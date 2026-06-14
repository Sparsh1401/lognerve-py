from enum import Enum

SDK_NAME = "lognerve-python-sdk"
SDK_VERSION = "0.1.0"
TRACER_NAME = "lognerve"

SPAN_KIND = "openinference.span.kind"
INPUT_VALUE = "input.value"
OUTPUT_VALUE = "output.value"
USER_ID = "user.id"
SESSION_ID = "session.id"

LLM_MODEL = "lognerve.llm.model"
LLM_MESSAGE = "lognerve.llm.message"
LLM_TOKEN_COUNT = "lognerve.token.count"
LLM_MODEL_PARAMETERS = "lognerve.model.parameters"

TRACE_METADATA = "lognerve.trace.metadata"
TRACE_TAGS = "lognerve.trace.tags"

SPAN_PATH = "lognerve.span.path"
SPAN_IDS_PATH = "lognerve.span.ids_path"
SPAN_SOURCE_FILE = "lognerve.git.source_file"
SPAN_SOURCE_LINE = "lognerve.git.source_line"
SPAN_SOURCE_FUNCTION = "lognerve.git.source_function"

GIT_REPO = "lognerve.git.repo"
GIT_REF = "lognerve.git.ref"


class SpanType(str, Enum):
    SPAN = "span"
    CHAIN = "chain"
    AGENT = "agent"
    TOOL = "tool"
    LLM = "llm"


SPAN_KIND_MAP = {
    SpanType.SPAN.value: "CHAIN",
    SpanType.CHAIN.value: "CHAIN",
    SpanType.AGENT.value: "AGENT",
    SpanType.TOOL.value: "TOOL",
    SpanType.LLM.value: "LLM",
}
