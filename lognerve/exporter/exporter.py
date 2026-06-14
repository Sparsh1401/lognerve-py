import logging

from opentelemetry.exporter.otlp.proto.http.trace_exporter import Compression, OTLPSpanExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SpanExporter, SpanExportResult

from lognerve.util.constants import SDK_NAME, SDK_VERSION

logger = logging.getLogger(__name__)


class _NoOpSpanExporter(SpanExporter):
    """Drops spans silently. Used when the OTLP exporter cannot be built so we
    never fall back to printing (potentially PII-bearing) attributes to stdout."""

    def export(self, spans):
        return SpanExportResult.SUCCESS

    def shutdown(self):
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def build_exporter(kind=None, api_key=None, otlp_endpoint=None, otlp_headers=None, otlp_compression=None):
    if kind in ("otlp-http", "otlp-proto"):
        if kind == "otlp-http":
            # The Python OTLP exporter only ships a protobuf-over-HTTP transport.
            # The LogNerve backend accepts both, so this is safe, but make the
            # divergence from the requested wire format explicit.
            logger.info("lognerve: 'otlp-http' uses the protobuf-over-HTTP transport in the Python SDK")
        try:
            return OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=build_headers(api_key=api_key, otlp_headers=otlp_headers),
                compression=Compression.Gzip if otlp_compression == "gzip" else None,
            )
        except Exception:
            # Do NOT fall back to ConsoleSpanExporter: it prints span attributes
            # (which may contain PII) to stdout. Drop export instead — local
            # console rendering is handled separately by LogNerveSpanProcessor.
            logger.warning("lognerve: OTLP exporter init failed — span export disabled", exc_info=True)
            return _NoOpSpanExporter()
    return ConsoleSpanExporter()


def build_headers(api_key=None, otlp_headers=None):
    headers = {
        "x-lognerve-sdk-name": SDK_NAME,
        "x-lognerve-sdk-version": SDK_VERSION,
    }
    if api_key is not None:
        headers["Authorization"] = "Bearer " + api_key
    if otlp_headers:
        headers.update(otlp_headers)
    return headers
