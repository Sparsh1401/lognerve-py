from lognerve.exporter.exporter import build_headers
from lognerve.shared.config import read_env


def test_build_headers_adds_sdk_identity_and_authorization():
    headers = build_headers(api_key="test-key")

    assert headers["x-lognerve-sdk-name"] == "lognerve-python-sdk"
    assert headers["x-lognerve-sdk-version"] == "0.1.1"
    assert headers["Authorization"] == "Bearer test-key"


def test_api_key_authorization_is_not_overridable_but_custom_headers_pass_through():
    headers = build_headers(
        api_key="generated-key",
        otlp_headers={"Authorization": "Bearer attacker-key", "x-custom": "yes"},
    )

    # The configured api_key is security-critical and must win over an injected
    # Authorization header (e.g. via LOGNERVE_OTLP_HEADERS).
    assert headers["Authorization"] == "Bearer generated-key"
    assert headers["x-custom"] == "yes"


def test_otlp_headers_authorization_applies_without_api_key():
    headers = build_headers(otlp_headers={"Authorization": "Bearer explicit-key"})

    assert headers["Authorization"] == "Bearer explicit-key"


def test_read_env_reads_lognerve_api_key(monkeypatch):
    monkeypatch.setenv("LOGNERVE_API_KEY", "env-key")

    assert read_env()["api_key"] == "env-key"
