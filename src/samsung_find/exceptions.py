"""Structured exception hierarchy for samsung-find."""

from __future__ import annotations


class SamsungFindError(Exception):
    """Base class for all Samsung Find exceptions."""

    def __init__(self, message: str, code: str = "general_error"):
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


class AuthError(SamsungFindError):
    """Authentication or authorization failure."""

    def __init__(self, message: str, code: str = "auth_required"):
        super().__init__(message, code=code)


class SecurityError(SamsungFindError):
    """Security validation failure (e.g. untrusted host, permission violation, symlink)."""

    def __init__(self, message: str, code: str = "security_violation"):
        super().__init__(message, code=code)


class NetworkError(SamsungFindError):
    """Network connection or remote protocol error."""

    def __init__(self, message: str, code: str = "network_error"):
        super().__init__(message, code=code)


class StorageError(SamsungFindError):
    """Local storage read/write/permission error."""

    def __init__(self, message: str, code: str = "storage_error"):
        super().__init__(message, code=code)


class DeviceNotFoundError(SamsungFindError):
    """Requested device was not found."""

    def __init__(self, message: str, code: str = "device_not_found"):
        super().__init__(message, code=code)


class RateLimitError(SamsungFindError):
    """Rate limit or backoff encountered."""

    def __init__(self, message: str, code: str = "rate_limit_exceeded"):
        super().__init__(message, code=code)


class OperationError(SamsungFindError):
    """Device operation failure or timeout."""

    def __init__(self, message: str, code: str = "operation_failed"):
        super().__init__(message, code=code)


# Backward compatibility alias
SamsungAuthError = AuthError
