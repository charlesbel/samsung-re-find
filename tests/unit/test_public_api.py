from unittest.mock import MagicMock

from samsung_find import (
    Device,
    DeviceCapabilities,
    FindConfig,
    LocationResult,
    OperationResult,
    SamsungFindClient,
)
from samsung_find.api import SamsungFindClient as LegacyTransportClient
from samsung_find.client import SamsungFindClient as FacadeClient
from samsung_find.exceptions import (
    AuthError,
    DeviceNotFoundError,
    SamsungFindError,
    SecurityError,
)
from samsung_find.service import FindService


def test_public_imports_available_at_root():
    assert SamsungFindClient is not None
    assert SamsungFindClient is FacadeClient
    assert LegacyTransportClient is not FacadeClient
    assert FindConfig is not None
    assert Device is not None
    assert DeviceCapabilities is not None
    assert LocationResult is not None
    assert OperationResult is not None
    assert SamsungFindError is not None
    assert AuthError is not None
    assert SecurityError is not None
    assert DeviceNotFoundError is not None


def test_models_repr_does_not_leak_secrets_or_ids():
    loc = LocationResult(
        latitude=48.8566,
        longitude=2.3522,
        accuracy_m=10.0,
        timestamp="2026-08-30T12:00:00Z",
        is_fresh=True,
    )
    assert repr(loc) is not None

    dev = Device(
        id="dev-12345678-secret-id",
        name="Galaxy Phone",
        model="SM-S928B",
        location_type="precise",
    )
    # Ensure ID is never in repr
    assert "dev-12345678-secret-id" not in repr(dev)
    assert "Galaxy Phone" in repr(dev)


def test_device_id_masking_by_default_and_opt_in():
    fake_transport = MagicMock()
    fake_transport.devices.return_value = [
        {
            "id": "secret-device-uuid-999",
            "name": "My Galaxy Phone",
            "model": "SM-S928B",
            "location_type": "precise",
        }
    ]
    service = FindService(client=fake_transport)
    client = FacadeClient(service=service)

    # 1. Default list_devices masks IDs
    devices_default = client.list_devices()
    assert len(devices_default) == 1
    d_default = devices_default[0]
    assert isinstance(d_default, Device)
    assert d_default.name == "My Galaxy Phone"
    assert d_default.id is None
    assert "id" not in d_default.to_dict()

    # 2. Opt-in includes IDs
    devices_with_id = client.list_devices(include_ids=True)
    assert len(devices_with_id) == 1
    d_with_id = devices_with_id[0]
    assert isinstance(d_with_id, Device)
    assert d_with_id.id == "secret-device-uuid-999"
    assert d_with_id.to_dict(include_id=True)["id"] == "secret-device-uuid-999"


def test_typed_facade_method_signatures_and_returns():
    fake_transport = MagicMock()
    fake_transport.capabilities.return_value = {
        "ring": True,
        "track": False,
        "locate": True,
        "check_connection": True,
        "features": ["ring", "locate"],
    }
    fake_transport.locate.return_value = {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "accuracy_m": 12.5,
        "is_fresh": True,
        "is_precise": True,
        "address": "Paris, France",
    }
    fake_transport.check_connection.return_value = {
        "reachable": True,
        "battery": "90",
        "request_id": "req-1",
    }
    fake_transport.ring.return_value = {
        "request_id": "req-2",
        "status_code": "200",
    }
    fake_transport.track.return_value = {
        "request_id": "req-3",
    }

    service = FindService(client=fake_transport)
    client = FacadeClient(service=service)

    # Capabilities
    caps = client.get_capabilities("Galaxy Phone")
    assert isinstance(caps, DeviceCapabilities)
    assert caps.can_ring is True
    assert caps.can_track is False
    assert not hasattr(caps, "raw") or getattr(caps, "raw", None) is None or caps.raw == {}

    # Last location
    loc = client.get_last_location("Galaxy Phone")
    assert isinstance(loc, LocationResult)
    assert loc.latitude == 48.8566
    assert loc.longitude == 2.3522
    assert loc.is_fresh is True

    # Request location
    req_loc = client.request_location("Galaxy Phone", poll_seconds=10)
    assert isinstance(req_loc, LocationResult)
    assert req_loc.latitude == 48.8566

    # Check connection
    conn = client.check_connection("Galaxy Phone")
    assert isinstance(conn, OperationResult)
    assert conn.operation == "CHECK_CONNECTION"
    assert conn.success is True
    assert conn.battery == "90"
    assert "details" not in conn.to_dict()

    # Ring
    ring_res = client.ring("Galaxy Phone", status="start")
    assert isinstance(ring_res, OperationResult)
    assert ring_res.operation == "RING"
    assert ring_res.success is True

    # Tracking
    track_res = client.set_tracking("Galaxy Phone", enabled=True)
    assert isinstance(track_res, OperationResult)
    assert track_res.operation == "TRACK_LOCATION_START"


def test_missing_coordinates_remain_none_not_fabricated():
    fake_transport = MagicMock()
    fake_transport.locate.return_value = {
        "accuracy_m": None,
        "is_fresh": False,
        "is_precise": False,
        "address": None,
    }
    service = FindService(client=fake_transport)
    client = FacadeClient(service=service)

    loc = client.get_last_location("Galaxy Phone")
    assert isinstance(loc, LocationResult)
    assert loc.latitude is None
    assert loc.longitude is None
    assert loc.accuracy_m is None
    assert loc.to_dict()["latitude"] is None
    assert loc.to_dict()["longitude"] is None


def test_facade_context_manager_closes_resources():
    fake_service = MagicMock()
    with FacadeClient(service=fake_service) as client:
        assert client is not None

    fake_service.close.assert_called_once()
