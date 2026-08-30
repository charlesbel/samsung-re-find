"""High-level application service layer for Samsung Find."""

from __future__ import annotations

from typing import Any

from .api import SamsungFindClient as _LegacyTransportClient
from .config import FindConfig
from .models import Device, DeviceCapabilities, LocationResult, OperationResult


def _parse_coordinate(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class FindService:
    """Service layer exposing typed domain operations."""

    def __init__(self, client: _LegacyTransportClient):
        self.client = client

    @classmethod
    def from_config(cls, config: FindConfig | None = None) -> FindService:
        client = _LegacyTransportClient.from_config(config)
        return cls(client)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> FindService:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def list_devices(self, *, include_ids: bool = False) -> list[Device]:
        raw_devices = self.client.devices()
        results: list[Device] = []
        for d in raw_devices:
            results.append(
                Device(
                    name=str(d.get("name", "Unknown")),
                    id=str(d.get("id")) if include_ids and d.get("id") is not None else None,
                    model=d.get("model"),
                    location_type=d.get("location_type"),
                    device_type=d.get("device_type"),
                )
            )
        return results

    def get_capabilities(self, query: str) -> DeviceCapabilities:
        raw_cap = self.client.capabilities(query)
        return DeviceCapabilities(
            can_ring=bool(raw_cap.get("ring")),
            can_track=bool(raw_cap.get("track")),
            can_locate=bool(raw_cap.get("locate", True)),
            can_check_connection=bool(raw_cap.get("check_connection")),
            offline_finding=bool(raw_cap.get("offline_finding")),
            features=list(raw_cap.get("features") or []),
        )

    def get_last_location(self, query: str) -> LocationResult:
        raw_loc = self.client.locate(query, active=False)
        return LocationResult(
            latitude=_parse_coordinate(raw_loc.get("latitude")),
            longitude=_parse_coordinate(raw_loc.get("longitude")),
            accuracy_m=_parse_float(raw_loc.get("accuracy_m")),
            timestamp=raw_loc.get("timestamp"),
            is_fresh=bool(raw_loc.get("is_fresh", False)),
            is_precise=bool(raw_loc.get("is_precise", False)),
            address=raw_loc.get("address"),
            map_url=raw_loc.get("map_url"),
        )

    def request_location(self, query: str, poll_seconds: int = 180) -> LocationResult:
        raw_loc = self.client.locate(query, active=True, poll_seconds=poll_seconds)
        return LocationResult(
            latitude=_parse_coordinate(raw_loc.get("latitude")),
            longitude=_parse_coordinate(raw_loc.get("longitude")),
            accuracy_m=_parse_float(raw_loc.get("accuracy_m")),
            timestamp=raw_loc.get("timestamp"),
            is_fresh=bool(raw_loc.get("is_fresh", True)),
            is_precise=bool(raw_loc.get("is_precise", True)),
            address=raw_loc.get("address"),
            map_url=raw_loc.get("map_url"),
        )

    def check_connection(self, query: str, poll_seconds: int = 40) -> OperationResult:
        raw_op = self.client.check_connection(query, poll_seconds=poll_seconds)
        return OperationResult(
            operation="CHECK_CONNECTION",
            success=bool(raw_op.get("reachable", True)),
            request_id=raw_op.get("request_id"),
            status_code=raw_op.get("status_code"),
            message=raw_op.get("message"),
            battery=str(raw_op.get("battery")) if raw_op.get("battery") is not None else None,
        )

    def ring(
        self,
        query: str,
        *,
        status: str = "start",
        message: str | None = None,
        poll_seconds: int = 40,
    ) -> OperationResult:
        raw_op = self.client.ring(query, status=status, message=message, poll_seconds=poll_seconds)
        return OperationResult(
            operation="RING",
            success=True,
            request_id=raw_op.get("request_id"),
            status_code=raw_op.get("status_code"),
            message=raw_op.get("message"),
        )

    def set_tracking(self, query: str, *, enabled: bool = True, poll_seconds: int = 30) -> OperationResult:
        raw_op = self.client.track(query, enabled=enabled, poll_seconds=poll_seconds)
        return OperationResult(
            operation="TRACK_LOCATION_START" if enabled else "TRACK_LOCATION_STOP",
            success=True,
            request_id=raw_op.get("request_id"),
            status_code=raw_op.get("status_code"),
            message=raw_op.get("message"),
        )
