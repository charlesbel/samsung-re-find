from unittest.mock import MagicMock

from samsung_find import (
    FIND_REQUESTER_NAME,
    FIND_REQUESTER_TOKEN,
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
    assert FIND_REQUESTER_NAME == "FIND_MY_MOBILE"
    assert FIND_REQUESTER_TOKEN == "b47285ea-2615-46eb-a1d2-28e4e94119d8"


def test_models_repr_does_not_leak_secrets_or_ids():
    loc = LocationResult(
        latitude=48.8566,
        longitude=2.3522,
        accuracy_m=10.0,
        timestamp="2026-08-30T12:00:00+00:00",
        is_fresh=True,
    )
    assert repr(loc) is not None

    dev = Device(
        id="dev-12345678-secret-id",
        name="Galaxy Phone",
        model="SM-S928B",
        location_type="PHONE",
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
            "location_type": "PHONE",
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
        "device": {"name": "Galaxy Phone", "model": "SM-S928B", "location_type": "PHONE"},
        "passive_location": True,
        "active_location": True,
        "connection_check": True,
        "battery_status": True,
        "ring": True,
        "continuous_tracking": False,
        "remote_lock": "discovered_not_exposed",
        "remote_wipe": "discovered_not_exposed",
    }
    fake_transport.locate.return_value = {
        "device": {"name": "Galaxy Phone", "model": "SM-S928B", "location_type": "PHONE"},
        "latitude": 48.8566,
        "longitude": 2.3522,
        "accuracy_m": 12.5,
        "last_update": "2026-08-30T12:00:00+00:00",
        "timezone": "UTC",
        "age_seconds": 45,
        "battery": "90",
        "operation": "LOCATION",
        "active_refresh_requested": True,
        "active_operation": {"accepted": True, "operation": {"result": "success"}},
        "fresh_location_obtained": True,
        "maps_url": "https://www.google.com/maps?q=48.8566,2.3522",
    }
    fake_transport.check_connection.return_value = {
        "device": {"name": "Galaxy Phone"},
        "requested_operation": "CHECK_CONNECTION",
        "accepted": True,
        "request_id": "req-1",
        "operation": {
            "type": "CHECK_CONNECTION",
            "status_code": "2800",
            "result_code": "1200",
            "result": "success",
            "battery_percent": 90,
        },
    }
    fake_transport.ring.return_value = {
        "device": {"name": "Galaxy Phone"},
        "requested_operation": "RING",
        "accepted": True,
        "request_id": "req-2",
        "operation": {
            "type": "RING",
            "status_code": "2800",
            "result_code": "1200",
            "result": "success",
            "battery_percent": None,
        },
    }
    fake_transport.track.return_value = {
        "device": {"name": "Galaxy Phone"},
        "requested_operation": "TRACK_LOCATION_START",
        "accepted": True,
        "request_id": "req-3",
        "operation": {
            "type": "TRACK_LOCATION_START",
            "status_code": "2100",
            "result_code": None,
            "result": "success",
            "battery_percent": None,
        },
    }

    service = FindService(client=fake_transport)
    client = FacadeClient(service=service)

    # Capabilities
    caps = client.get_capabilities("Galaxy Phone")
    assert isinstance(caps, DeviceCapabilities)
    assert caps.can_ring is True
    assert caps.can_track is False
    assert caps.passive_location is True
    assert caps.active_location is True
    assert caps.battery_status is True
    assert not hasattr(caps, "raw")

    # Last location
    loc = client.get_last_location("Galaxy Phone")
    assert isinstance(loc, LocationResult)
    assert loc.latitude == 48.8566
    assert loc.longitude == 2.3522
    assert loc.timestamp == "2026-08-30T12:00:00+00:00"
    assert loc.is_fresh is True
    assert loc.is_precise is True
    assert loc.map_url == "https://www.google.com/maps?q=48.8566,2.3522"

    # Request location
    req_loc = client.request_location("Galaxy Phone", poll_seconds=10)
    assert isinstance(req_loc, LocationResult)
    assert req_loc.latitude == 48.8566

    # Check connection
    conn = client.check_connection("Galaxy Phone")
    assert isinstance(conn, OperationResult)
    assert conn.operation == "CHECK_CONNECTION"
    assert conn.accepted is True
    assert conn.success is True
    assert conn.battery == "90"
    assert conn.request_id == "req-1"

    # Ring
    ring_res = client.ring("Galaxy Phone", status="start")
    assert isinstance(ring_res, OperationResult)
    assert ring_res.operation == "RING"
    assert ring_res.accepted is True
    assert ring_res.success is True
    assert ring_res.request_id == "req-2"

    # Tracking
    track_res = client.set_tracking("Galaxy Phone", enabled=True)
    assert isinstance(track_res, OperationResult)
    assert track_res.operation == "TRACK_LOCATION_START"
    assert track_res.accepted is True
    assert track_res.success is True
    assert track_res.request_id == "req-3"


def test_missing_coordinates_and_metadata_remain_none():
    fake_transport = MagicMock()
    fake_transport.locate.return_value = {
        "device": {"name": "Galaxy Watch", "location_type": "UNKNOWN"},
        "latitude": None,
        "longitude": None,
        "accuracy_m": None,
        "last_update": None,
        "timezone": "UTC",
        "age_seconds": None,
        "battery": None,
        "operation": None,
        "active_refresh_requested": False,
        "active_operation": None,
        "fresh_location_obtained": False,
        "maps_url": None,
    }
    service = FindService(client=fake_transport)
    client = FacadeClient(service=service)

    loc = client.get_last_location("Galaxy Watch")
    assert isinstance(loc, LocationResult)
    assert loc.latitude is None
    assert loc.longitude is None
    assert loc.accuracy_m is None
    assert loc.timestamp is None
    assert loc.is_fresh is False
    assert loc.is_precise is False
    assert loc.map_url is None
    assert loc.to_dict()["latitude"] is None
    assert loc.to_dict()["longitude"] is None


def test_facade_context_manager_closes_resources():
    fake_service = MagicMock()
    with FacadeClient(service=fake_service) as client:
        assert client is not None

    fake_service.close.assert_called_once()


def test_facade_constructors_and_location_redaction(tmp_path):
    # 1. LocationResult repr/str redacts sensitive info
    loc = LocationResult(
        latitude=48.8566,
        longitude=2.3522,
        accuracy_m=10.0,
        timestamp="2026-08-30T12:00:00+00:00",
        map_url="https://maps.google.com/?q=48.8566,2.3522",
    )
    for text in (repr(loc), str(loc)):
        assert "48.8566" not in text
        assert "2.3522" not in text
        assert "maps.google.com" not in text
        assert "2026-08-30" not in text
        assert "[REDACTED]" in text

    # 2. Constructor with auth
    from samsung_find.auth import SamsungAuth

    auth = SamsungAuth(state_path=tmp_path / "state.json", master_path=tmp_path / "master.json")
    client_auth = SamsungFindClient(auth=auth)
    assert client_auth is not None
    client_auth.close()

    # 3. Constructor with config
    config = FindConfig(country="FR", language="fr", timezone="Europe/Paris")
    client_cfg = SamsungFindClient(config=config)
    assert client_cfg is not None
    client_cfg.close()

    # 4. Constructor default
    client_def = SamsungFindClient()
    assert client_def is not None
    client_def.close()

    # 5. Constructor from_config
    client_from_cfg = SamsungFindClient.from_config(config)
    assert client_from_cfg is not None
    client_from_cfg.close()
