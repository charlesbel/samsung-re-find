from unittest.mock import MagicMock

from samsung_find.models import Device, DeviceCapabilities, LocationResult, OperationResult
from samsung_find.service import FindService


def test_find_service_list_devices_id_masking():
    mock_client = MagicMock()
    mock_client.devices.return_value = [
        {"id": "secret-d1", "name": "Galaxy S24", "model": "SM-S928B", "location_type": "PHONE"}
    ]

    service = FindService(mock_client)

    # 1. Default masks id
    devices = service.list_devices()
    assert len(devices) == 1
    assert isinstance(devices[0], Device)
    assert devices[0].name == "Galaxy S24"
    assert devices[0].id is None
    assert "id" not in devices[0].to_dict()

    # 2. Opt-in includes id
    devices_opt_in = service.list_devices(include_ids=True)
    assert devices_opt_in[0].id == "secret-d1"
    assert devices_opt_in[0].to_dict(include_id=True)["id"] == "secret-d1"


def test_find_service_capabilities_real_transport_shape():
    mock_client = MagicMock()
    # Real transport shape from api.py capabilities()
    mock_client.capabilities.return_value = {
        "device": {"name": "Galaxy S24", "model": "SM-S928B", "location_type": "PHONE"},
        "passive_location": True,
        "active_location": True,
        "connection_check": True,
        "battery_status": True,
        "ring": True,
        "continuous_tracking": True,
        "remote_lock": "discovered_not_exposed",
        "remote_wipe": "discovered_not_exposed",
    }

    service = FindService(mock_client)
    caps = service.get_capabilities("Galaxy S24")

    assert isinstance(caps, DeviceCapabilities)
    assert caps.can_ring is True
    assert caps.can_track is True
    assert caps.can_locate is True
    assert caps.can_check_connection is True
    assert caps.passive_location is True
    assert caps.active_location is True
    assert caps.battery_status is True


def test_find_service_location_real_transport_shape():
    mock_client = MagicMock()
    # Real transport shape from api.py locate()
    mock_client.locate.return_value = {
        "device": {"name": "Galaxy S24", "model": "SM-S928B", "location_type": "PHONE"},
        "latitude": 48.8566,
        "longitude": 2.3522,
        "accuracy_m": 12.0,
        "last_update": "2026-08-30T12:00:00+00:00",
        "timezone": "UTC",
        "age_seconds": 30,
        "battery": "95",
        "operation": "LOCATION",
        "active_refresh_requested": True,
        "active_operation": {"accepted": True, "operation": {"result": "success"}},
        "fresh_location_obtained": True,
        "maps_url": "https://www.google.com/maps?q=48.8566,2.3522",
    }

    service = FindService(mock_client)
    loc = service.get_last_location("Galaxy S24")

    assert isinstance(loc, LocationResult)
    assert loc.latitude == 48.8566
    assert loc.longitude == 2.3522
    assert loc.accuracy_m == 12.0
    assert loc.timestamp == "2026-08-30T12:00:00+00:00"
    assert loc.is_fresh is True
    assert loc.is_precise is True
    assert loc.map_url == "https://www.google.com/maps?q=48.8566,2.3522"
    assert loc.battery == "95"


def test_find_service_operations_success_in_progress_and_failed():
    mock_client = MagicMock()

    # 1. Success operation
    mock_client.ring.return_value = {
        "device": {"name": "Galaxy S24"},
        "requested_operation": "RING",
        "accepted": True,
        "request_id": "req-ring-1",
        "operation": {
            "type": "RING",
            "status_code": "2800",
            "result_code": "1200",
            "result": "success",
            "battery_percent": 85,
        },
    }

    service = FindService(mock_client)
    ring_res = service.ring("Galaxy S24")
    assert isinstance(ring_res, OperationResult)
    assert ring_res.accepted is True
    assert ring_res.success is True
    assert ring_res.operation == "RING"
    assert ring_res.request_id == "req-ring-1"
    assert ring_res.battery == "85"
    assert ring_res.result == "success"

    # 2. In progress operation
    mock_client.check_connection.return_value = {
        "device": {"name": "Galaxy S24"},
        "requested_operation": "CHECK_CONNECTION",
        "accepted": True,
        "request_id": "req-check-2",
        "operation": {
            "type": "CHECK_CONNECTION",
            "status_code": "2100",
            "result_code": None,
            "result": "in_progress",
            "battery_percent": None,
        },
    }
    check_res = service.check_connection("Galaxy S24")
    assert check_res.accepted is True
    assert check_res.success is False
    assert check_res.result == "in_progress"

    # 3. Failed operation
    mock_client.track.return_value = {
        "device": {"name": "Galaxy S24"},
        "requested_operation": "TRACK_LOCATION_START",
        "accepted": True,
        "request_id": "req-track-3",
        "operation": {
            "type": "TRACK_LOCATION_START",
            "status_code": "2900",
            "result_code": "01",
            "result": "failed",
            "battery_percent": None,
        },
    }
    track_res = service.set_tracking("Galaxy S24", enabled=True)
    assert track_res.accepted is True
    assert track_res.success is False
    assert track_res.result == "failed"
