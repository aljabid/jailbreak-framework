from __future__ import annotations

import re
from typing import Any

SECRET_PATTERNS = [
    (
        re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}\b"),
        "[REDACTED:API_KEY]",
    ),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
        "Bearer [REDACTED:TOKEN]",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|secret)"
            r"(\s*[:=]\s*)[^\s,;]{8,}"
        ),
        r"\1\2[REDACTED:SECRET]",
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED:PRIVATE_KEY]",
    ),
]

PII_PATTERNS = [
    (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        "[REDACTED:EMAIL]",
    ),
    (
        re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
        "[REDACTED:PHONE]",
    ),
]


def redact_text(value: str, include_pii: bool = False) -> str:
    redacted = value
    patterns = SECRET_PATTERNS + (PII_PATTERNS if include_pii else [])
    for pattern, replacement in patterns:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_value(value: Any, include_pii: bool = False) -> Any:

    if isinstance(value, str):
        return redact_text(value, include_pii=include_pii)
    if isinstance(value, dict):
        return {key: redact_value(item, include_pii=include_pii) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, include_pii=include_pii) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item, include_pii=include_pii) for item in value)
    return value


def markdown_inline(value: Any) -> str:

    text = redact_text(str(value), include_pii=True)
    return (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )
