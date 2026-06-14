import os
from typing import Dict, Optional

from lognerve.instrumentation.instrumentation import parse_integrations


def read_env() -> Dict[str, object]:
    return {
        "api_key": os.getenv("LOGNERVE_API_KEY"),
        "domain": os.getenv("LOGNERVE_DOMAIN"),
        "project_name": os.getenv("LOGNERVE_PROJECT_NAME"),
        "service_name": os.getenv("LOGNERVE_SERVICE_NAME"),
        "git_repo": os.getenv("LOGNERVE_GIT_REPO"),
        "git_ref": os.getenv("LOGNERVE_GIT_REF"),
        "otlp_endpoint": os.getenv("LOGNERVE_OTLP_ENDPOINT"),
        "otlp_headers": parse_headers(os.getenv("LOGNERVE_OTLP_HEADERS")),
        "otlp_compression": parse_compression(os.getenv("LOGNERVE_OTLP_COMPRESSION")),
        "batch_export": parse_bool(os.getenv("LOGNERVE_BATCH_EXPORT")),
        "exporter": parse_exporter(os.getenv("LOGNERVE_EXPORTER")),
        "environment": parse_environment(os.getenv("LOGNERVE_ENVIRONMENT")),
        "enabled": parse_bool(os.getenv("LOGNERVE_ENABLED"), True),
        "redact_pii": parse_bool(os.getenv("LOGNERVE_REDACT_PII")),
    }


def read_instrumentations():
    raw = os.getenv("LOGNERVE_INSTRUMENTATIONS")
    return parse_integrations(raw.split(",") if raw else [])


def parse_headers(raw: Optional[str]):
    if not raw:
        return None
    headers = {}
    for pair in raw.split(","):
        key, _, value = pair.partition("=")
        if key.strip():
            headers[key.strip()] = value.strip()
    return headers


def parse_exporter(raw: Optional[str]):
    return raw if raw in ("console", "otlp-http", "otlp-proto") else None


def parse_environment(raw: Optional[str]):
    if raw == "development":
        return "local"
    return raw if raw in ("local", "production") else None


def parse_compression(raw: Optional[str]):
    return raw if raw in ("none", "gzip") else None


def parse_bool(raw: Optional[str], default=None):
    if raw is None:
        return default
    if raw.lower() in ("true", "1", "yes", "on"):
        return True
    if raw.lower() in ("false", "0", "no", "off"):
        return False
    return default
