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
        passive_loc = bool(raw_cap.get("passive_location", False))
        active_loc = bool(raw_cap.get("active_location", False))
        return DeviceCapabilities(
            can_ring=bool(raw_cap.get("ring", False)),
            can_track=bool(raw_cap.get("continuous_tracking", False)),
            can_locate=passive_loc or active_loc,
            can_check_connection=bool(raw_cap.get("connection_check", False)),
            passive_location=passive_loc,
            active_location=active_loc,
            battery_status=bool(raw_cap.get("battery_status", False)),
        )

    def _map_location_result(self, raw_loc: dict[str, Any]) -> LocationResult:
        device_info = raw_loc.get("device") or {}
        loc_type = str(device_info.get("location_type") or "").upper()
        # Location is precise if reported by precise device types (e.g. Phone, Tablet, or GPS type codes)
        is_precise = loc_type in {"1", "3", "PHONE", "TAB", "PRECISE"}

        battery = raw_loc.get("battery")
        battery_str = str(battery) if battery is not None else None

        age_sec = raw_loc.get("age_seconds")
        try:
            age_sec = int(age_sec) if age_sec is not None else None
        except (ValueError, TypeError):
            age_sec = None

        return LocationResult(
            latitude=_parse_coordinate(raw_loc.get("latitude")),
            longitude=_parse_coordinate(raw_loc.get("longitude")),
            accuracy_m=_parse_float(raw_loc.get("accuracy_m")),
            timestamp=raw_loc.get("last_update"),
            is_fresh=bool(raw_loc.get("fresh_location_obtained", False)),
            is_precise=is_precise,
            map_url=raw_loc.get("maps_url"),
            timezone=raw_loc.get("timezone"),
            age_seconds=age_sec,
            battery=battery_str,
            operation=raw_loc.get("operation"),
            active_refresh_requested=bool(raw_loc.get("active_refresh_requested", False)),
        )

    def get_last_location(self, query: str) -> LocationResult:
        raw_loc = self.client.locate(query, active=False)
        return self._map_location_result(raw_loc)

    def request_location(self, query: str, *, poll_seconds: int = 180) -> LocationResult:
        raw_loc = self.client.locate(query, active=True, poll_seconds=poll_seconds)
        return self._map_location_result(raw_loc)

    def _map_operation_result(self, raw_op: dict[str, Any], default_op: str) -> OperationResult:
        accepted = bool(raw_op.get("accepted", False))
        op_details = raw_op.get("operation") or {}
        result_label = op_details.get("result")
        success = accepted and (result_label == "success")

        status_code = op_details.get("status_code")
        result_code = op_details.get("result_code")
        battery_pct = op_details.get("battery_percent")
        battery_str = str(battery_pct) if battery_pct is not None else None

        return OperationResult(
            operation=str(raw_op.get("requested_operation") or default_op),
            accepted=accepted,
            success=success,
            request_id=raw_op.get("request_id"),
            status_code=str(status_code) if status_code is not None else None,
            result_code=str(result_code) if result_code is not None else None,
            result=str(result_label) if result_label is not None else None,
            battery=battery_str,
            message=raw_op.get("message") or op_details.get("message"),
        )

    def check_connection(self, query: str, *, poll_seconds: int = 40) -> OperationResult:
        raw_op = self.client.check_connection(query, poll_seconds=poll_seconds)
        return self._map_operation_result(raw_op, "CHECK_CONNECTION")

    def ring(
        self,
        query: str,
        *,
        status: str = "start",
        message: str | None = None,
        poll_seconds: int = 40,
    ) -> OperationResult:
        raw_op = self.client.ring(query, status=status, message=message, poll_seconds=poll_seconds)
        return self._map_operation_result(raw_op, "RING")

    def set_tracking(
        self,
        query: str,
        *,
        enabled: bool = True,
        poll_seconds: int = 30,
    ) -> OperationResult:
        raw_op = self.client.track(query, enabled=enabled, poll_seconds=poll_seconds)
        default_op = "TRACK_LOCATION_START" if enabled else "TRACK_LOCATION_STOP"
        return self._map_operation_result(raw_op, default_op)
