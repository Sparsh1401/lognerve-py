import re
from typing import Any, Dict, Iterable, List, Optional, Pattern, Tuple, Union

PiiEntity = str
PiiConfig = Union[bool, Dict[str, Any]]

DEFAULT_ENTITIES = ["email", "phone", "credit_card", "ssn", "ip_address", "api_key"]
DEFAULT_REPLACEMENT = "[REDACTED]"

# Strings longer than this are skipped by redaction to bound ReDoS exposure from
# user-supplied patterns (catastrophic backtracking is triggered by long input).
MAX_REDACTABLE_LENGTH = 100_000


class PiiRedactor:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.replacement = config.get("replacement") or DEFAULT_REPLACEMENT
        entities = config.get("entities") or DEFAULT_ENTITIES
        self.rules = [_build_rule(entity, self.replacement) for entity in entities]
        for rule in config.get("patterns") or []:
            pattern = rule.get("pattern") if isinstance(rule, dict) else None
            if not pattern:
                continue
            self.rules.append(
                (
                    rule.get("name") or "custom",
                    re.compile(pattern),
                    rule.get("replacement") or self.replacement,
                    None,
                )
            )

    def redact(self, value: Any) -> Any:
        return self._redact_value(value, set())

    def _redact_value(self, value: Any, seen: set) -> Any:
        if isinstance(value, str):
            return self._redact_string(value)
        if isinstance(value, list):
            return [self._redact_value(item, seen) for item in value]
        if isinstance(value, tuple):
            return tuple(self._redact_value(item, seen) for item in value)
        if isinstance(value, dict):
            marker = id(value)
            if marker in seen:
                return value
            seen.add(marker)
            return {key: self._redact_value(nested, seen) for key, nested in value.items()}
        return value

    def _redact_string(self, value: str) -> str:
        if len(value) > MAX_REDACTABLE_LENGTH:
            return value
        redacted = value
        for entity, pattern, replacement, validator in self.rules:
            def replace(match):
                text = match.group(0)
                if validator is not None and not validator(text):
                    return text
                return replacement.replace("{entity}", entity)

            redacted = pattern.sub(replace, redacted)
        return redacted


def create_pii_redactor(config: Optional[PiiConfig]) -> Optional[PiiRedactor]:
    if config is None or config is False:
        return None
    if config is True:
        return PiiRedactor()
    if isinstance(config, dict) and config.get("enabled") is False:
        return None
    return PiiRedactor(config if isinstance(config, dict) else {})


def _build_rule(entity: PiiEntity, replacement: str) -> Tuple[str, Pattern[str], str, Any]:
    normalized = entity.replace("-", "_")
    if normalized == "email":
        return (normalized, re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), replacement, None)
    if normalized == "phone":
        return (normalized, re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b"), replacement, None)
    if normalized in ("credit_card", "creditCard"):
        return (normalized, re.compile(r"\b(?:\d[ -]*?){13,19}\b"), replacement, _is_likely_credit_card)
    if normalized == "ssn":
        return (normalized, re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), replacement, None)
    if normalized in ("ip_address", "ipAddress"):
        return (normalized, re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), replacement, _is_ipv4)
    # Covers generic prefixed keys (sk_/pk_/rk_/lnv_), OpenAI project keys
    # (sk-proj-...), Anthropic keys (sk-ant-...), AWS access key ids (AKIA...),
    # GitHub tokens (ghp_/gho_/ghu_/ghs_/ghr_), and Bearer tokens.
    return (
        normalized,
        re.compile(
            r"\b(?:sk|pk|rk|lnv)_[A-Za-z0-9_-]{16,}\b"
            r"|\bsk-(?:proj|ant|or)-[A-Za-z0-9_-]{16,}\b"
            r"|\bAKIA[0-9A-Z]{16}\b"
            r"|\bgh[pousr]_[A-Za-z0-9]{36,}\b"
            r"|\bBearer\s+[A-Za-z0-9._\-+/=]{12,}\b"
        ),
        replacement,
        None,
    )


def _is_likely_credit_card(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    double = False
    for char in reversed(digits):
        digit = int(char)
        if double:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        double = not double
    return total % 10 == 0


def _is_ipv4(value: str) -> bool:
    try:
        return all(0 <= int(part) <= 255 for part in value.split("."))
    except ValueError:
        return False
