import copy
import re
from typing import Any


RESIDENT_REGISTRATION_RE = re.compile(r"\b(\d{6})-?(\d)(\d{6})\b")
PHONE_RE = re.compile(r"\b(0(?:2|[3-9]\d|10|11|16|17|18|19))[-.\s]?(\d{3,4})[-.\s]?(\d{4})\b")

NAME_KEYS = {"name", "representative_name", "contract_money_received_by"}
RESIDENT_KEYS = {"resident_registration_number", "rrn"}
PHONE_KEYS = {"phone", "tel", "mobile", "telephone", "contact"}


def mask_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) <= 1:
        return text
    if len(text) == 2:
        return text[0] + "*"
    return text[0] + ("*" * (len(text) - 2)) + text[-1]


def mask_resident_registration_number(value: str | None) -> str | None:
    if value is None:
        return None

    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}-{match.group(2)}******"

    return RESIDENT_REGISTRATION_RE.sub(replace, str(value))


def mask_phone_number(value: str | None) -> str | None:
    if value is None:
        return None

    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}-{match.group(2)}-****"

    return PHONE_RE.sub(replace, str(value))


def _text_value(node: Any) -> str | None:
    if isinstance(node, dict):
        for key in ("value", "raw_text", "normalized_value"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(node, str) and node.strip():
        return node.strip()
    return None


def _collect_known_names(data: Any) -> set[str]:
    names: set[str] = set()

    def walk(node: Any, key: str | None = None) -> None:
        if isinstance(node, dict):
            if key in NAME_KEYS:
                value = _text_value(node)
                if value:
                    names.add(value)
            for child_key, child_value in node.items():
                walk(child_value, child_key)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif key in NAME_KEYS and isinstance(node, str) and node.strip():
            names.add(node.strip())

    walk(data)
    return names


def mask_sensitive_text(value: str, known_names: set[str] | None = None) -> str:
    text = mask_resident_registration_number(value) or value
    text = mask_phone_number(text) or text
    for name in sorted(known_names or set(), key=len, reverse=True):
        masked = mask_name(name)
        if masked and masked != name:
            text = text.replace(name, masked)
    return text


def mask_sensitive_data(data: Any, known_names: set[str] | None = None) -> Any:
    names = known_names or _collect_known_names(data)

    def walk(node: Any, key: str | None = None) -> Any:
        if isinstance(node, dict):
            return {child_key: walk(child_value, child_key) for child_key, child_value in node.items()}
        if isinstance(node, list):
            return [walk(item, key) for item in node]
        if isinstance(node, str):
            lowered_key = (key or "").lower()
            if lowered_key in NAME_KEYS:
                return mask_name(node)
            if lowered_key in RESIDENT_KEYS:
                return mask_resident_registration_number(node)
            if lowered_key in PHONE_KEYS:
                return mask_phone_number(node)
            return mask_sensitive_text(node, names)
        return node

    return walk(copy.deepcopy(data))


def build_public_result(result: dict[str, Any]) -> dict[str, Any]:
    return mask_sensitive_data(result)
