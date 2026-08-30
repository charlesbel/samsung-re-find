from unittest.mock import MagicMock

from samsung_find.models import Device, DeviceCapabilities, LocationResult
from samsung_find.service import FindService


def test_find_service_list_devices():
    mock_client = MagicMock()
    mock_client.devices.return_value = [
        {"id": "d1", "name": "Galaxy S24", "model": "SM-S928B", "location_type": "precise"}
    ]

    service = FindService(mock_client)
    devices = service.list_devices()

    assert len(devices) == 1
    assert isinstance(devices[0], Device)
    assert devices[0].name == "Galaxy S24"
    assert devices[0].model == "SM-S928B"


def test_find_service_get_capabilities():
    mock_client = MagicMock()
    mock_client.capabilities.return_value = {
        "ring": True,
        "track": False,
        "locate": True,
        "check_connection": True,
        "features": ["RING", "LOCATION"],
    }

    service = FindService(mock_client)
    caps = service.get_capabilities("Galaxy S24")

    assert isinstance(caps, DeviceCapabilities)
    assert caps.can_ring is True
    assert caps.can_track is False
    assert "RING" in caps.features


def test_find_service_location():
    mock_client = MagicMock()
    mock_client.locate.return_value = {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "accuracy_m": 10.0,
        "is_fresh": True,
        "is_precise": True,
        "timestamp": "2026-08-30T12:00:00Z",
    }

    service = FindService(mock_client)
    loc = service.get_last_location("Galaxy S24")

    assert isinstance(loc, LocationResult)
    assert loc.latitude == 48.8566
    assert loc.longitude == 2.3522
    assert loc.is_fresh is True
