# LogNerve Python SDK

Small Python SDK for tracing agentic and LLM applications with LogNerve.

```bash
pip install lognerve
```

```python
import lognerve

lognerve.initialize(
    api_key="lnv_sk_p3zI8Nnk3VkD-P0rBfjSTeWd4XCA6l-IrEmI3rWyFTI",
    domain="api.lognerve.ai",
    project_name="agent-examples",
    service_name="vanilla-tool-loop",
    exporter="otlp-http",
    redact_pii=True,
)

@lognerve.observe(name="workflow", type="agent")
def run_workflow(goal: str) -> str:
    return "done"

run_workflow("test tracing")
```

The root package intentionally exposes only `lognerve.initialize`, `lognerve.observe`, and `lognerve.usingAttributes`.

When neither `otlp_endpoint` nor `domain` is set, the SDK defaults to `https://lognerve.ai/api/v1/traces`. Use `domain` to customize (e.g. `https://eu.lognerve.ai/api/v1/traces`). Explicit `otlp_endpoint` always takes precedence.

Set `LOGNERVE_REDACT_PII=true` or pass `redact_pii=True` to redact common PII locally before span export. Default local redaction covers emails, phone numbers, credit cards, SSNs, IPv4 addresses, API keys, and bearer tokens. You can customize it with `redact_pii={"entities": ["email", "api_key"], "patterns": [{"pattern": "customer-[0-9]+"}]}`.

SOC 2, encryption at rest, server-side intelligent PII detection, and on-prem alerting are backend/product controls. The SDK control implemented here is local regex redaction before export.

When `api_key` or `LOGNERVE_API_KEY` is set, OTLP requests include `Authorization: Bearer <api_key>`. Explicit `otlp_headers={"Authorization": ...}` or `LOGNERVE_OTLP_HEADERS` overrides the generated header.
