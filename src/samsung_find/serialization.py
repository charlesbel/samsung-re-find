"""Serialization and versioned envelope wrappers for CLI and API responses."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION_V1 = "1.0"


def to_serializable(obj: Any) -> Any:
    """Recursively convert dataclasses and objects to clean serializable dicts."""
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_serializable(item) for item in obj]
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=UTC)
        return obj.isoformat()
    return obj


def serialize_response(
    data: Any,
    meta: dict[str, Any] | None = None,
    schema_version: str = SCHEMA_VERSION_V1,
) -> dict[str, Any]:
    """Wrap output in standardized v1 success envelope."""
    payload: dict[str, Any] = {
        "ok": True,
        "schema_version": schema_version,
        "data": to_serializable(data),
    }
    if meta is not None:
        payload["meta"] = to_serializable(meta)
    return payload


def serialize_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    schema_version: str = SCHEMA_VERSION_V1,
) -> dict[str, Any]:
    """Wrap failure in standardized v1 error envelope."""
    err_obj: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details:
        err_obj["details"] = to_serializable(details)

    return {
        "ok": False,
        "schema_version": schema_version,
        "error": err_obj,
    }


def to_json(
    value: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> str:
    """Format serialized data to a deterministic JSON string."""
    return json.dumps(to_serializable(value), indent=indent, ensure_ascii=ensure_ascii, sort_keys=True)
