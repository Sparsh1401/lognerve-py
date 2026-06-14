import logging
import re
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

from lognerve.exporter.exporter import build_exporter
from lognerve.shared.config import read_env
from lognerve.shared.git import read_git_context
from lognerve.tracer.processor import LogNerveSpanProcessor
from lognerve.util.constants import GIT_REF, GIT_REPO

logger = logging.getLogger(__name__)


class TraceHandle:
    def __init__(self, provider: TracerProvider):
        self.provider = provider

    def flush(self) -> None:
        self.provider.force_flush()

    def shutdown(self) -> None:
        self.provider.shutdown()


def create(**config):
    env = read_env()
    merged = {**env, **{key: value for key, value in config.items() if value is not None}}
    if merged.get("enabled") is False:
        return None
    # Default to backend export (protobuf + gzip). The LogNerve backend accepts
    # OTLP/proto and OTLP/JSON; proto matches the OpenInference default and the
    # underlying exporter, and gzip keeps every backend-bound payload compressed.
    # Devs can still set exporter="console" for local-only runs.
    if merged.get("exporter") is None:
        merged["exporter"] = "otlp-proto"
    if merged.get("environment") is None:
        merged["environment"] = "production"
    if merged.get("otlp_compression") is None:
        merged["otlp_compression"] = "gzip"
    if merged.get("otlp_endpoint") is None:
        merged["otlp_endpoint"] = f"https://{merged.get('domain') or 'lognerve.ai'}/api/v1/traces"
    _assert_safe_endpoint(merged["otlp_endpoint"])
    git = read_git_context(merged.get("git_repo"), merged.get("git_ref"))
    attributes = {"service.name": merged.get("service_name") or "lognerve-app", "project.name": merged.get("project_name") or "lognerve-default"}
    if merged.get("environment"):
        attributes["deployment.environment"] = merged["environment"]
    if git.get("git_repo"):
        attributes[GIT_REPO] = git["git_repo"]
    if git.get("git_ref"):
        attributes[GIT_REF] = git["git_ref"]

    provider = TracerProvider(resource=Resource.create(attributes))
    provider.add_span_processor(LogNerveSpanProcessor(git_repo=git.get("git_repo"), git_ref=git.get("git_ref"), dev_mode=merged.get("environment") == "local", redact_pii=merged.get("redact_pii")))
    exporter = build_exporter(
        merged.get("exporter"),
        merged.get("api_key"),
        merged.get("otlp_endpoint"),
        merged.get("otlp_headers"),
        merged.get("otlp_compression"),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter) if merged.get("batch_export") else SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return TraceHandle(provider)


def _assert_safe_endpoint(endpoint: str) -> None:
    """Validate the resolved export endpoint before any telemetry (which can
    carry LLM prompts/completions and the API key) leaves the process."""
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        logger.warning("lognerve: invalid otlp_endpoint %r; export may fail", endpoint)
        return
    if parsed.scheme != "https":
        # http:// sends the Authorization: Bearer <api_key> header in cleartext.
        logger.warning(
            "lognerve: insecure otlp_endpoint %r — use https:// so the API key and trace data are not sent in plaintext",
            endpoint,
        )
    if _is_private_or_metadata_host(parsed.hostname or ""):
        # SSRF guard: a poisoned LOGNERVE_DOMAIN/LOGNERVE_OTLP_ENDPOINT could
        # redirect telemetry to the cloud metadata service or an internal host.
        logger.warning(
            "lognerve: otlp_endpoint host %r is a private/link-local address; refusing it as a default target",
            parsed.hostname,
        )


def _is_private_or_metadata_host(hostname: str) -> bool:
    host = hostname.strip("[]")
    if host in ("localhost", "::1"):
        return True
    match = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", host)
    if not match:
        return False
    a, b = int(match.group(1)), int(match.group(2))
    if a in (0, 10, 127):
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 169 and b == 254:  # link-local / cloud metadata
        return True
    return False
