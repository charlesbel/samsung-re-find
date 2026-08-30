"""Public typed client facade for Samsung Find."""

from __future__ import annotations

from typing import Any

from .api import SamsungFindClient as _LegacyTransportClient
from .auth import SamsungAuth
from .config import FindConfig
from .models import Device, DeviceCapabilities, LocationResult, OperationResult
from .service import FindService


class SamsungFindClient:
    """Public typed SDK facade for Samsung SmartThings Find."""

    def __init__(
        self,
        service: FindService | None = None,
        *,
        auth: SamsungAuth | None = None,
        config: FindConfig | None = None,
    ):
        if service is not None:
            self._service = service
        elif config is not None:
            self._service = FindService.from_config(config)
        else:
            cfg = FindConfig()
            transport = _LegacyTransportClient(auth or SamsungAuth(), config=cfg)
            self._service = FindService(transport)

    @classmethod
    def from_config(cls, config: FindConfig | None = None) -> SamsungFindClient:
        cfg = config or FindConfig()
        service = FindService.from_config(cfg)
        return cls(service=service)

    def close(self) -> None:
        self._service.close()

    def __enter__(self) -> SamsungFindClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def list_devices(self, *, include_ids: bool = False) -> list[Device]:
        """List all Samsung Find devices registered to account.

        Device IDs are masked (None) by default to prevent leaking internal identifiers.
        Pass `include_ids=True` to opt-in to raw device identifiers.
        """
        return self._service.list_devices(include_ids=include_ids)

    def get_capabilities(self, query: str) -> DeviceCapabilities:
        """Get safe supported capability flags for device matching query."""
        return self._service.get_capabilities(query)

    def get_last_location(self, query: str) -> LocationResult:
        """Get last known GPS location without sending active device ping."""
        return self._service.get_last_location(query)

    def request_location(self, query: str, *, poll_seconds: int = 180) -> LocationResult:
        """Request active GPS fix refresh and poll for fresh coordinates."""
        return self._service.request_location(query, poll_seconds=poll_seconds)

    def check_connection(self, query: str, *, poll_seconds: int = 40) -> OperationResult:
        """Ping device to verify connectivity and battery state."""
        return self._service.check_connection(query, poll_seconds=poll_seconds)

    def ring(
        self,
        query: str,
        *,
        status: str = "start",
        message: str | None = None,
        poll_seconds: int = 40,
    ) -> OperationResult:
        """Audibly ring device (status='start') or stop alarm (status='stop')."""
        return self._service.ring(query, status=status, message=message, poll_seconds=poll_seconds)

    def set_tracking(
        self,
        query: str,
        *,
        enabled: bool = True,
        poll_seconds: int = 30,
    ) -> OperationResult:
        """Toggle continuous lost-mode tracking on device."""
        return self._service.set_tracking(query, enabled=enabled, poll_seconds=poll_seconds)
