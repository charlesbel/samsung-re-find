"""Domain and SDK models for Samsung Find."""

from __future__ import annotations

from dataclasses import dataclass
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
    passive_location: bool = True
    active_location: bool = True
    battery_status: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_ring": self.can_ring,
            "can_track": self.can_track,
            "can_locate": self.can_locate,
            "can_check_connection": self.can_check_connection,
            "passive_location": self.passive_location,
            "active_location": self.active_location,
            "battery_status": self.battery_status,
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
    map_url: str | None = None
    timezone: str | None = None
    age_seconds: int | None = None
    battery: str | None = None
    operation: str | None = None
    active_refresh_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_m": self.accuracy_m,
            "timestamp": self.timestamp,
            "is_fresh": self.is_fresh,
            "is_precise": self.is_precise,
            "map_url": self.map_url,
        }
        if self.timezone is not None:
            data["timezone"] = self.timezone
        if self.age_seconds is not None:
            data["age_seconds"] = self.age_seconds
        if self.battery is not None:
            data["battery"] = self.battery
        if self.operation is not None:
            data["operation"] = self.operation
        if self.active_refresh_requested:
            data["active_refresh_requested"] = self.active_refresh_requested
        return data


@dataclass(frozen=True)
class OperationResult:
    """Result of an active operation (ring, track, check_connection, etc.)."""

    operation: str
    accepted: bool = False
    success: bool = False
    request_id: str | None = None
    status_code: str | None = None
    result_code: str | None = None
    result: str | None = None
    battery: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "operation": self.operation,
            "accepted": self.accepted,
            "success": self.success,
        }
        if self.request_id is not None:
            data["request_id"] = self.request_id
        if self.status_code is not None:
            data["status_code"] = self.status_code
        if self.result_code is not None:
            data["result_code"] = self.result_code
        if self.result is not None:
            data["result"] = self.result
        if self.battery is not None:
            data["battery"] = self.battery
        if self.message is not None:
            data["message"] = self.message
        return data
