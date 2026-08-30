"""Domain and SDK models for Samsung Find."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Device:
    """Represents a Samsung device or tag discovered via Samsung Find."""

    name: str
    id: str | None = None
    model: str | None = None
    location_type: str | None = None
    device_type: str | None = None

    def __repr__(self) -> str:
        return (
            f"Device(name={self.name!r}, model={self.model!r}, "
            f"location_type={self.location_type!r}, device_type={self.device_type!r})"
        )

    def to_dict(self, *, include_id: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "model": self.model,
            "location_type": self.location_type,
            "device_type": self.device_type,
        }
        if include_id and self.id is not None:
            data["id"] = self.id
        return data


@dataclass(frozen=True)
class DeviceCapabilities:
    """Supported safe capabilities for a device."""

    can_ring: bool = False
    can_track: bool = False
    can_locate: bool = True
    can_check_connection: bool = False
    offline_finding: bool = False
    features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_ring": self.can_ring,
            "can_track": self.can_track,
            "can_locate": self.can_locate,
            "can_check_connection": self.can_check_connection,
            "offline_finding": self.offline_finding,
            "features": list(self.features),
        }


@dataclass(frozen=True)
class LocationResult:
    """Location coordinate and status report for a device."""

    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    timestamp: str | None = None
    is_fresh: bool = False
    is_precise: bool = False
    address: str | None = None
    map_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_m": self.accuracy_m,
            "timestamp": self.timestamp,
            "is_fresh": self.is_fresh,
            "is_precise": self.is_precise,
            "address": self.address,
            "map_url": self.map_url,
        }


@dataclass(frozen=True)
class OperationResult:
    """Result of an active operation (ring, track, check_connection, etc.)."""

    operation: str
    success: bool
    request_id: str | None = None
    status_code: str | None = None
    message: str | None = None
    battery: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "operation": self.operation,
            "success": self.success,
            "request_id": self.request_id,
            "status_code": self.status_code,
            "message": self.message,
        }
        if self.battery is not None:
            data["battery"] = self.battery
        return data
