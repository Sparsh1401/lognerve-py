import atexit
import logging
import threading

from lognerve.instrumentation.instrumentation import initialize_integrations, parse_integrations
from lognerve.shared.config import read_instrumentations
from lognerve.tracer.tracer import create

logger = logging.getLogger(__name__)

_client = None
_lock = threading.Lock()


class LogNerveClient:
    def __init__(self, handle, instrumented):
        self.handle = handle
        self.instrumented = list(instrumented)

    @property
    def enabled(self) -> bool:
        return self.handle is not None

    def flush(self) -> None:
        try:
            if self.handle is not None:
                self.handle.flush()
        except Exception:
            logger.debug("lognerve: flush failed (harmless)", exc_info=True)

    def shutdown(self) -> None:
        try:
            if self.handle is not None:
                self.handle.shutdown()
        except Exception:
            logger.debug("lognerve: shutdown failed (harmless)", exc_info=True)
        finally:
            self.handle = None


def initialize(instrumentations=None, **config) -> LogNerveClient:
    global _client
    with _lock:
        if _client is not None:
            return _client
        try:
            handle = create(**config)
            raw_instrumentations = instrumentations if instrumentations is not None else read_instrumentations()
            parsed = parse_integrations(raw_instrumentations)
            instrumented = initialize_integrations(handle.provider, parsed) if handle is not None else []
            _client = LogNerveClient(handle, instrumented)
            atexit.register(shutdown)
        except Exception:
            logger.warning("lognerve: initialize() failed — tracing disabled", exc_info=True)
            _client = LogNerveClient(None, [])
        return _client


def flush() -> None:
    try:
        if _client is not None:
            _client.flush()
    except Exception:
        pass


def shutdown() -> None:
    global _client
    try:
        if _client is not None:
            _client.shutdown()
    except Exception:
        pass
    finally:
        _client = None
