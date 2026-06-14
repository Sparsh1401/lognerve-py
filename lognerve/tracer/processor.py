import logging
import sys
import threading
import time
from collections import OrderedDict

from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

from lognerve.privacy.pii import create_pii_redactor
from lognerve.util.constants import GIT_REF, GIT_REPO, SDK_NAME, SDK_VERSION, SPAN_IDS_PATH, SPAN_KIND, SPAN_PATH

logger = logging.getLogger(__name__)


class LogNerveSpanProcessor(SpanProcessor):
    def __init__(self, git_repo=None, git_ref=None, dev_mode=False, redact_pii=None):
        self.git_repo = git_repo
        self.git_ref = git_ref
        self.dev_mode = dev_mode
        self.pii_redactor = create_pii_redactor(redact_pii)
        self._lock = threading.RLock()
        self._ids_path_by_span_id = OrderedDict()
        self._name_path_by_span_id = OrderedDict()
        self._start_by_span_id = {}

    def on_start(self, span: Span, parent_context=None) -> None:
        try:
            if not span.is_recording():
                return
            span.set_attribute("lognerve.sdk.name", SDK_NAME)
            span.set_attribute("lognerve.sdk.version", SDK_VERSION)
            if self.git_repo is not None:
                span.set_attribute(GIT_REPO, self.git_repo)
            if self.git_ref is not None:
                span.set_attribute(GIT_REF, self.git_ref)

            parent = getattr(span, "parent", None)
            parent_id = format(parent.span_id, "016x") if parent is not None and getattr(parent, "is_valid", False) else None
            with self._lock:
                parent_ids_path = self._ids_path_by_span_id.get(parent_id) if parent_id else None
                parent_name_path = self._name_path_by_span_id.get(parent_id) if parent_id else None
                span_name = getattr(span, "name", "") or ""
                span_path = parent_name_path + [span_name] if parent_name_path else [span_name]
                span_ids_path = parent_ids_path + [parent_id] if parent_id and parent_ids_path else ([parent_id] if parent_id else [])
                span_id = format(span.context.span_id, "016x")
                self._ids_path_by_span_id[span_id] = span_ids_path
                self._name_path_by_span_id[span_id] = span_path
                self._start_by_span_id[span_id] = time.monotonic()
            span.set_attribute(SPAN_PATH, span_path)
            span.set_attribute(SPAN_IDS_PATH, span_ids_path)
        except Exception:
            logger.debug("lognerve: on_start failed (harmless)", exc_info=True)

    def on_end(self, span: ReadableSpan) -> None:
        try:
            span_id = format(span.context.span_id, "016x")
            with self._lock:
                self._ids_path_by_span_id.pop(span_id, None)
                self._name_path_by_span_id.pop(span_id, None)
                started = self._start_by_span_id.pop(span_id, None)
            self._redact_span(span)
            if self.dev_mode:
                duration_ms = (time.monotonic() - started) * 1000 if started else 0
                kind = span.attributes.get(SPAN_KIND, "SPAN")
                sys.stdout.write(f"[lognerve] {str(kind).lower()}  {span.name}  {duration_ms:.0f}ms\n")
        except Exception:
            logger.debug("lognerve: on_end failed (harmless)", exc_info=True)

    def shutdown(self) -> None:
        self._ids_path_by_span_id.clear()
        self._name_path_by_span_id.clear()
        self._start_by_span_id.clear()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def _redact_span(self, span: ReadableSpan) -> None:
        if self.pii_redactor is None:
            return
        # ReadableSpan exposes `name` (read-only property) and `attributes`
        # (immutable MappingProxyType). Redaction must therefore mutate the
        # underlying mutable backing fields `_name` and `_attributes`
        # (a BoundedAttributes MutableMapping). Assigning to the public
        # properties silently raises AttributeError/TypeError, which would
        # leave PII unredacted.
        try:
            self._redact_mutable(span)
            for event in getattr(span, "events", []) or []:
                self._redact_mutable(event)
        except Exception:
            # Redaction mutates in place; a failure here may leave some
            # attributes unredacted. Surface at WARNING (not DEBUG) so the
            # potential leak is observable in production logs.
            logger.warning("lognerve: pii redaction failed — some data may be unredacted", exc_info=True)

    def _redact_mutable(self, target) -> None:
        name = getattr(target, "_name", None)
        if isinstance(name, str):
            target._name = self.pii_redactor.redact(name)
        attributes = getattr(target, "_attributes", None)
        if not attributes:
            return
        redacted = {key: self.pii_redactor.redact(value) for key, value in attributes.items()}
        try:
            # Span attributes are a mutable BoundedAttributes — redact in place.
            for key, value in redacted.items():
                attributes[key] = value
        except (TypeError, AttributeError):
            # Event attributes use an immutable BoundedAttributes; assignment
            # raises, so replace the backing mapping wholesale instead.
            target._attributes = redacted
