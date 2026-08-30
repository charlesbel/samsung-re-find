"""Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .client import SamsungFindClient
from .config import FindConfig
from .constants import FIND_REQUESTER_NAME, FIND_REQUESTER_TOKEN
from .credentials import MasterState, MasterStateStore, resolve_master_state_path
from .exceptions import (
    AuthError,
    DeviceNotFoundError,
    NetworkError,
    OperationError,
    RateLimitError,
    SamsungAuthError,
    SamsungFindError,
    SecurityError,
    StorageError,
)
from .models import Device, DeviceCapabilities, LocationResult, OperationResult

try:
    __version__ = version("samsung-re-find")
except PackageNotFoundError:
    try:
        __version__ = version("samsung-find")
    except PackageNotFoundError:
        try:
            __version__ = version("samsung-find-agent")
        except PackageNotFoundError:
            __version__ = "0.2.0"

__all__ = [
    "AuthError",
    "Device",
    "DeviceCapabilities",
    "DeviceNotFoundError",
    "FIND_REQUESTER_NAME",
    "FIND_REQUESTER_TOKEN",
    "FindConfig",
    "LocationResult",
    "MasterState",
    "MasterStateStore",
    "NetworkError",
    "OperationError",
    "OperationResult",
    "RateLimitError",
    "SamsungAuthError",
    "SamsungFindClient",
    "SamsungFindError",
    "SecurityError",
    "StorageError",
    "__version__",
    "resolve_master_state_path",
]
