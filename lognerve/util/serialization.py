import json
from typing import Any, Optional


def try_serialize(value: Any) -> Optional[str]:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return None


def set_json_attribute(span: Any, key: str, value: Any) -> None:
    if value is None:
        return
    serialized = try_serialize(value)
    if serialized is not None:
        span.set_attribute(key, serialized)
