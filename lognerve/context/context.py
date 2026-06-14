import functools
import inspect
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from lognerve.shared.git import capture_source_location
from lognerve.util.constants import (
    INPUT_VALUE,
    LLM_MODEL,
    LLM_MODEL_PARAMETERS,
    LLM_TOKEN_COUNT,
    OUTPUT_VALUE,
    SESSION_ID,
    SPAN_KIND,
    SPAN_KIND_MAP,
    SPAN_SOURCE_FILE,
    SPAN_SOURCE_FUNCTION,
    SPAN_SOURCE_LINE,
    TRACE_METADATA,
    TRACE_TAGS,
    TRACER_NAME,
    USER_ID,
)
from lognerve.util.serialization import set_json_attribute

logger = logging.getLogger(__name__)

try:
    from openinference.instrumentation import get_attributes_from_context
    from openinference.instrumentation import using_attributes as _using_attributes
except Exception:  # pragma: no cover - only used if optional dep import shape changes
    get_attributes_from_context = None
    _using_attributes = None

F = TypeVar("F", bound=Callable[..., Any])


def observe(
    name: Optional[str] = None,
    type: str = "span",
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    capture_input: bool = True,
    capture_output: bool = True,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        span_name = name or func.__name__ or "anonymous"

        if inspect.isasyncgenfunction(func):
            return _wrap_async_generator_function(
                func,
                span_name,
                type,
                metadata,
                tags,
                capture_input,
                capture_output,
                session_id,
                user_id,
            )
        if inspect.isgeneratorfunction(func):
            return _wrap_generator_function(
                func,
                span_name,
                type,
                metadata,
                tags,
                capture_input,
                capture_output,
                session_id,
                user_id,
            )
        if inspect.iscoroutinefunction(func):
            return _wrap_async_function(
                func,
                span_name,
                type,
                metadata,
                tags,
                capture_input,
                capture_output,
                session_id,
                user_id,
            )
        return _wrap_sync_function(
            func,
            span_name,
            type,
            metadata,
            tags,
            capture_input,
            capture_output,
            session_id,
            user_id,
        )

    return decorator


@contextmanager
def using_attributes(**kwargs: Any) -> Iterator[None]:
    if _using_attributes is None:
        yield
        return
    with _using_attributes(**kwargs):
        yield


def set_attributes(
    name: Optional[str] = None,
    input: Any = None,
    output: Any = None,
    model: Optional[str] = None,
    model_params: Optional[Dict[str, Any]] = None,
    usage: Optional[Dict[str, int]] = None,
) -> None:
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return

    if name is not None:
        span.update_name(name)
    set_json_attribute(span, INPUT_VALUE, input)
    set_json_attribute(span, OUTPUT_VALUE, output)
    if model is not None:
        span.set_attribute(LLM_MODEL, model)
    set_json_attribute(span, LLM_MODEL_PARAMETERS, model_params)
    set_json_attribute(span, LLM_TOKEN_COUNT, usage)


def set_trace_attributes(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return

    if session_id is not None:
        span.set_attribute(SESSION_ID, session_id)
    if user_id is not None:
        span.set_attribute(USER_ID, user_id)
    set_json_attribute(span, TRACE_TAGS, tags)
    set_json_attribute(span, TRACE_METADATA, metadata)


def get_active_trace_id():
    span = trace.get_current_span()
    context = span.get_span_context()
    if context and context.is_valid:
        return format(context.trace_id, "032x")
    return None


def get_active_span_id():
    span = trace.get_current_span()
    context = span.get_span_context()
    if context and context.is_valid:
        return format(context.span_id, "016x")
    return None


class Context:
    observe = staticmethod(observe)
    using_attributes = staticmethod(using_attributes)
    set_attributes = staticmethod(set_attributes)
    set_trace_attributes = staticmethod(set_trace_attributes)
    get_active_trace_id = staticmethod(get_active_trace_id)
    get_active_span_id = staticmethod(get_active_span_id)


def _wrap_sync_function(func, span_name, span_type, metadata, tags, capture_input, capture_output, session_id, user_id):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tracer = trace.get_tracer(TRACER_NAME)
        with tracer.start_as_current_span(span_name) as span:
            _apply_common_attributes(span, span_type, metadata, tags, args, kwargs, func, capture_input, session_id, user_id)
            try:
                result = func(*args, **kwargs)
                if capture_output and result is not None:
                    set_json_attribute(span, OUTPUT_VALUE, result)
                return result
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise

    return wrapper


def _wrap_async_function(func, span_name, span_type, metadata, tags, capture_input, capture_output, session_id, user_id):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        tracer = trace.get_tracer(TRACER_NAME)
        with tracer.start_as_current_span(span_name) as span:
            _apply_common_attributes(span, span_type, metadata, tags, args, kwargs, func, capture_input, session_id, user_id)
            try:
                result = await func(*args, **kwargs)
                if capture_output and result is not None:
                    set_json_attribute(span, OUTPUT_VALUE, result)
                return result
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise

    return wrapper


def _wrap_generator_function(func, span_name, span_type, metadata, tags, capture_input, capture_output, session_id, user_id):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tracer = trace.get_tracer(TRACER_NAME)
        span = tracer.start_span(span_name)
        _apply_common_attributes(span, span_type, metadata, tags, args, kwargs, func, capture_input, session_id, user_id)
        gen = func(*args, **kwargs)
        collected = []
        failed = False
        try:
            while True:
                try:
                    with trace.use_span(span, end_on_exit=False):
                        item = next(gen)
                except StopIteration:
                    break
                collected.append(item)
                yield item
        except GeneratorExit:
            try:
                gen.close()
            finally:
                raise
        except Exception as exc:
            failed = True
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
        finally:
            if not failed and capture_output and collected:
                set_json_attribute(span, OUTPUT_VALUE, collected)
            span.end()

    return wrapper


def _wrap_async_generator_function(func, span_name, span_type, metadata, tags, capture_input, capture_output, session_id, user_id):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        tracer = trace.get_tracer(TRACER_NAME)
        span = tracer.start_span(span_name)
        _apply_common_attributes(span, span_type, metadata, tags, args, kwargs, func, capture_input, session_id, user_id)
        gen = func(*args, **kwargs)
        collected = []
        failed = False
        try:
            while True:
                try:
                    with trace.use_span(span, end_on_exit=False):
                        item = await gen.__anext__()
                except StopAsyncIteration:
                    break
                collected.append(item)
                yield item
        except Exception as exc:
            failed = True
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
        finally:
            await gen.aclose()
            if not failed and capture_output and collected:
                set_json_attribute(span, OUTPUT_VALUE, collected)
            span.end()

    return wrapper


def _apply_common_attributes(span, span_type, metadata, tags, args, kwargs, func, capture_input, session_id, user_id):
    try:
        span.set_attribute(SPAN_KIND, SPAN_KIND_MAP.get(str(span_type), "CHAIN"))

        if get_attributes_from_context is not None:
            try:
                context_attrs = get_attributes_from_context()
                items = context_attrs.items() if hasattr(context_attrs, "items") else context_attrs
                for key, value in items:
                    span.set_attribute(key, value)
            except Exception:
                pass

        if session_id is not None:
            span.set_attribute(SESSION_ID, session_id)
        if user_id is not None:
            span.set_attribute(USER_ID, user_id)

        if capture_input:
            set_json_attribute(span, INPUT_VALUE, _capture_input(args, kwargs, func))
        set_json_attribute(span, TRACE_METADATA, metadata)
        set_json_attribute(span, TRACE_TAGS, tags)

        source = capture_source_location()
        if source.get("file") is not None:
            span.set_attribute(SPAN_SOURCE_FILE, source["file"])
        if source.get("line") is not None:
            span.set_attribute(SPAN_SOURCE_LINE, source["line"])
        if source.get("function") is not None:
            span.set_attribute(SPAN_SOURCE_FUNCTION, source["function"])
    except Exception:
        logger.debug("lognerve: _apply_common_attributes failed (harmless)", exc_info=True)


def _capture_input(args, kwargs, func):
    try:
        signature = inspect.signature(func)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        values = {key: value for key, value in bound.arguments.items() if key not in ("self", "cls")}
        if len(values) == 1:
            return next(iter(values.values()))
        return values
    except Exception:
        if kwargs:
            return {"args": args, "kwargs": kwargs}
        if len(args) == 1:
            return args[0]
        return args
