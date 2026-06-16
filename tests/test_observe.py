import asyncio
import json

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import lognerve
from lognerve.privacy.pii import PiiRedactor
from lognerve.tracer.processor import LogNerveSpanProcessor

SPAN_KIND = "openinference.span.kind"
INPUT_VALUE = "input.value"
OUTPUT_VALUE = "output.value"

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)


def setup_function():
    exporter.clear()


def test_root_package_api_is_minimal():
    assert sorted(lognerve.__all__) == ["flush", "initialize", "observe", "shutdown", "usingAttributes"]
    assert callable(lognerve.initialize)
    assert callable(lognerve.observe)
    assert callable(lognerve.usingAttributes)
    assert callable(lognerve.flush)
    assert callable(lognerve.shutdown)


def test_redacts_common_pii_with_local_regex_rules():
    redactor = PiiRedactor({"patterns": [{"pattern": "customer-[0-9]+", "replacement": "[CUSTOMER_ID]"}]})

    assert redactor.redact(
        "email jane@example.com phone 415-555-1212 card 4111 1111 1111 1111 token Bearer abcdefghijklmnop customer-42"
    ) == "email [REDACTED] phone [REDACTED] card [REDACTED] token [REDACTED] [CUSTOMER_ID]"


def test_span_processor_redacts_attributes_before_export():
    # Use a real OpenTelemetry span (not a stand-in object): ReadableSpan.name
    # and .attributes are read-only, so redaction must mutate the underlying
    # backing fields. A fake object with writable public attributes would hide
    # that the redaction path is broken.
    processor = LogNerveSpanProcessor(redact_pii=True)
    tracer = TracerProvider().get_tracer("redaction-test")
    span = tracer.start_span("pii jane@example.com")
    span.set_attribute(INPUT_VALUE, json.dumps("call me at 415-555-1212"))
    span.set_attribute(OUTPUT_VALUE, json.dumps({"answer": "email jane@example.com"}))
    span.add_event("Bearer abcdefghijklmnopqrstuvwx", {"token": "lnv_abcdefghijklmnopqrst"})
    span.end()

    processor._redact_span(span)

    assert span.name == "pii [REDACTED]"
    assert span.attributes[INPUT_VALUE] == json.dumps("call me at [REDACTED]")
    assert span.attributes[OUTPUT_VALUE] == json.dumps({"answer": "email [REDACTED]"})
    assert "jane@example.com" not in json.dumps(dict(span.attributes))
    assert span.events[0].name == "[REDACTED]"
    assert span.events[0].attributes["token"] == "[REDACTED]"


def test_observe_sync_function_captures_core_attributes():
    @lognerve.observe(name="add", type="tool", session_id="session-1", user_id="user-1", tags=["test"], metadata={"case": "sync"})
    def add(left, right):
        return left + right

    assert add(2, 3) == 5

    span = exporter.get_finished_spans()[0]
    assert span.name == "add"
    assert span.attributes[SPAN_KIND] == "TOOL"
    assert span.attributes[INPUT_VALUE] == json.dumps({"left": 2, "right": 3})
    assert span.attributes[OUTPUT_VALUE] == json.dumps(5)
    assert span.attributes["session.id"] == "session-1"
    assert span.attributes["user.id"] == "user-1"
    assert span.attributes["lognerve.trace.tags"] == json.dumps(["test"])
    assert span.attributes["lognerve.trace.metadata"] == json.dumps({"case": "sync"})
    assert isinstance(span.attributes["lognerve.git.source_file"], str)
    assert isinstance(span.attributes["lognerve.git.source_line"], int)


def test_observe_async_function_and_manual_update():
    @lognerve.observe(name="llm-call", type="llm")
    async def call_model(prompt):
        return {"answer": prompt.upper()}

    result = asyncio.run(call_model("hello"))

    assert result == {"answer": "HELLO"}
    span = exporter.get_finished_spans()[0]
    assert span.name == "llm-call"
    assert span.attributes[SPAN_KIND] == "LLM"


def test_nested_spans_have_parent_child_relationship():
    @lognerve.observe(name="child", type="tool")
    def child():
        return "child"

    @lognerve.observe(name="parent", type="agent")
    def parent():
        return child()

    assert parent() == "child"
    spans = exporter.get_finished_spans()
    parent_span = next(span for span in spans if span.name == "parent")
    child_span = next(span for span in spans if span.name == "child")
    assert child_span.parent.span_id == parent_span.context.span_id


def test_sync_generator_stays_open_and_records_chunks():
    @lognerve.observe(name="stream", type="llm")
    def stream(prefix):
        yield prefix + "-1"
        yield prefix + "-2"

    assert list(stream("chunk")) == ["chunk-1", "chunk-2"]
    span = exporter.get_finished_spans()[0]
    assert span.name == "stream"
    assert span.attributes[OUTPUT_VALUE] == json.dumps(["chunk-1", "chunk-2"])


def test_async_generator_stays_open_and_records_chunks():
    @lognerve.observe(name="async-stream", type="llm")
    async def stream(prefix):
        yield prefix + "-1"
        yield prefix + "-2"

    async def collect():
        chunks = []
        async for chunk in stream("chunk"):
            chunks.append(chunk)
        return chunks

    assert asyncio.run(collect()) == ["chunk-1", "chunk-2"]
    span = exporter.get_finished_spans()[0]
    assert span.name == "async-stream"
    assert span.attributes[OUTPUT_VALUE] == json.dumps(["chunk-1", "chunk-2"])


def test_async_generator_early_close_records_partial_output():
    closed = False

    @lognerve.observe(name="early-close", type="llm")
    async def stream():
        nonlocal closed
        try:
            yield "first"
            yield "second"
        finally:
            closed = True

    async def consume_one():
        async for _chunk in stream():
            break

    asyncio.run(consume_one())
    span = exporter.get_finished_spans()[0]
    assert closed is True
    assert span.attributes[OUTPUT_VALUE] == json.dumps(["first"])
