from lognerve.exporter.exporter import build_headers
from lognerve.shared.config import read_env


def test_build_headers_adds_sdk_identity_and_authorization():
    headers = build_headers(api_key="test-key")

    assert headers["x-lognerve-sdk-name"] == "lognerve-python-sdk"
    assert headers["x-lognerve-sdk-version"] == "0.1.0"
    assert headers["Authorization"] == "Bearer test-key"


def test_build_headers_allows_explicit_authorization_override():
    headers = build_headers(
        api_key="generated-key",
        otlp_headers={"Authorization": "Bearer explicit-key", "x-custom": "yes"},
    )

    assert headers["Authorization"] == "Bearer explicit-key"
    assert headers["x-custom"] == "yes"


def test_read_env_reads_lognerve_api_key(monkeypatch):
    monkeypatch.setenv("LOGNERVE_API_KEY", "env-key")

    assert read_env()["api_key"] == "env-key"
