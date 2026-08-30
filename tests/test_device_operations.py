from __future__ import annotations

import json
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from samsung_find.api import SamsungFindClient
from samsung_find.auth import SamsungAuthError


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {"content-type": "text/plain;charset=ISO-8859-1"}
        self.content = json.dumps(self._payload).encode()

    def json(self):
        return self._payload


class FakeWeb:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    def close(self):
        pass


def client_with_devices(devices):
    client = SamsungFindClient.__new__(SamsungFindClient)
    client.timezone = ZoneInfo("UTC")
    client.devices = lambda: devices
    return client


def phone():
    return {
        "id": "device-1",
        "name": "Primary Galaxy Phone",
        "model": "SM-TEST1",
        "location_type": "PHONE DEVICE",
        "user_id": "user-1",
        "raw": {"deviceType": "PHONE", "subType": None},
    }


def test_resolve_device_matches_name_model_and_rejects_ambiguity():
    client = client_with_devices(
        [
            phone(),
            {**phone(), "id": "device-2", "name": "Backup Galaxy Phone", "model": "SM-TEST2"},
        ]
    )
    assert client.resolve_device("SM-TEST1")["name"] == "Primary Galaxy Phone"
    with pytest.raises(SamsungAuthError, match="ambiguous"):
        client.resolve_device("Galaxy Phone")


def test_capabilities_are_conservative_for_phone():
    client = client_with_devices([phone()])
    capabilities = client.capabilities("Primary Galaxy")
    assert capabilities["ring"] is True
    assert capabilities["connection_check"] is True
    assert capabilities["continuous_tracking"] is True
    assert capabilities["remote_wipe"] == "discovered_not_exposed"
    assert capabilities["remote_lock"] == "discovered_not_exposed"


def test_ring_sends_expected_payload_and_returns_sanitized_result(monkeypatch):
    client = client_with_devices([phone()])
    web = FakeWeb(
        [
            FakeResponse(payload={"resultCode": "00", "reqId": "request-1", "oprnType": "RING"}),
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "RING",
                            "oprnStsCd": "2800",
                            "oprnResultCode": "1200",
                            "oprnCrtDate": "20260825100000",
                            "oprnDoneDate": "20260825100005",
                            "reqId": "request-1",
                            "privateField": "must-not-leak",
                        }
                    ]
                }
            ),
        ]
    )
    client._web_session = lambda: (web, "csrf")
    monkeypatch.setattr("samsung_find.api.time.sleep", lambda _seconds: None)

    result = client.ring("Primary Galaxy", status="start", message="Find request", poll_seconds=1)

    add_url, add_kwargs = web.calls[0]
    assert add_url.endswith("/dm/addOperation.do")
    assert add_kwargs["json"] == {
        "dvceId": "device-1",
        "operation": "RING",
        "usrId": "user-1",
        "status": "start",
        "lockMessage": "Find request",
    }
    assert result["accepted"] is True
    assert result["operation"]["result"] == "success"
    assert "privateField" not in json.dumps(result)


def test_connection_check_returns_battery(monkeypatch):
    client = client_with_devices([phone()])
    web = FakeWeb(
        [
            FakeResponse(payload={"resultCode": "00", "reqId": "request-2", "oprnType": "CHECK_CONNECTION"}),
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "CHECK_CONNECTION",
                            "oprnStsCd": "2800",
                            "oprnResultCode": "1200",
                            "oprnCrtDate": "20260825100201",
                            "oprnDoneDate": "20260825100202",
                            "battery": "80",
                            "reqId": "request-2",
                        }
                    ]
                }
            ),
        ]
    )
    client._web_session = lambda: (web, "csrf")
    monkeypatch.setattr("samsung_find.api.time.sleep", lambda _seconds: None)

    result = client.check_connection("Primary Galaxy", poll_seconds=1)

    assert result["accepted"] is True
    assert result["operation"]["battery_percent"] == 80
    assert result["operation"]["result"] == "success"


def test_connection_check_polls_past_in_progress(monkeypatch):
    client = client_with_devices([phone()])
    web = FakeWeb(
        [
            FakeResponse(payload={"resultCode": "00", "reqId": "request-3"}),
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "CHECK_CONNECTION",
                            "oprnStsCd": "1000",
                            "oprnResultCode": "200",
                            "reqId": "request-3",
                        }
                    ]
                }
            ),
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "CHECK_CONNECTION",
                            "oprnStsCd": "2800",
                            "oprnResultCode": "1200",
                            "battery": "75",
                            "reqId": "request-3",
                        }
                    ]
                }
            ),
        ]
    )
    client._web_session = lambda: (web, "csrf")
    ticks = iter([0.0, 0.0, 0.1, 0.2, 0.3])
    monkeypatch.setattr("samsung_find.api.time.monotonic", lambda: next(ticks, 0.3))
    monkeypatch.setattr("samsung_find.api.time.sleep", lambda _seconds: None)

    result = client.check_connection("Primary Galaxy", poll_seconds=1)

    assert result["operation"]["result"] == "success"
    assert result["operation"]["battery_percent"] == 75
    assert len(web.calls) == 3


def test_operation_poll_ignores_stale_request_ids(monkeypatch):
    client = client_with_devices([phone()])
    web = FakeWeb(
        [
            FakeResponse(payload={"resultCode": "00", "reqId": "new-request"}),
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "CHECK_CONNECTION",
                            "oprnStsCd": "2800",
                            "oprnResultCode": "1200",
                            "battery": "10",
                            "reqId": "old-request",
                        }
                    ]
                }
            ),
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "CHECK_CONNECTION",
                            "oprnStsCd": "2800",
                            "oprnResultCode": "1200",
                            "battery": "80",
                            "reqId": "new-request",
                        }
                    ]
                }
            ),
        ]
    )
    client._web_session = lambda: (web, "csrf")
    ticks = iter([0.0, 0.0, 0.1, 0.2, 0.3])
    monkeypatch.setattr("samsung_find.api.time.monotonic", lambda: next(ticks, 0.3))
    monkeypatch.setattr("samsung_find.api.time.sleep", lambda _seconds: None)

    result = client.check_connection("Primary Galaxy", poll_seconds=1)

    assert result["operation"]["battery_percent"] == 80
    assert "request_id" not in json.dumps(result)


def test_operation_fails_closed_when_acceptance_omits_request_id(monkeypatch):
    client = client_with_devices([phone()])
    web = FakeWeb(
        [
            FakeResponse(payload={"resultCode": "00"}),
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "CHECK_CONNECTION",
                            "oprnStsCd": "2800",
                            "oprnResultCode": "1200",
                            "reqId": "old-request",
                        }
                    ]
                }
            ),
        ]
    )
    client._web_session = lambda: (web, "csrf")
    monkeypatch.setattr("samsung_find.api.time.sleep", lambda _seconds: None)

    with pytest.raises(SamsungAuthError, match="omitted request id"):
        client.check_connection("Primary Galaxy", poll_seconds=1)


def test_locate_uses_direct_location_operation_and_detects_fresh_fix(monkeypatch):
    client = client_with_devices([phone()])
    old = FakeWeb(
        [
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "LOCATION",
                            "latitude": 10.0,
                            "longitude": 20.0,
                            "horizontalUncertainty": "10",
                            "verticalUncertainty": "0",
                            "extra": {"gpsUtcDt": "20260817075739"},
                        }
                    ]
                }
            )
        ]
    )
    fresh = FakeWeb(
        [
            FakeResponse(
                payload={
                    "operation": [
                        {
                            "oprnType": "LOCATION",
                            "latitude": 11.0,
                            "longitude": 21.0,
                            "horizontalUncertainty": "5",
                            "verticalUncertainty": "0",
                            "extra": {"gpsUtcDt": "20260825100731"},
                        }
                    ]
                }
            )
        ]
    )
    sessions = iter([(old, "csrf-old"), (fresh, "csrf-new")])
    client._web_session = lambda: next(sessions)
    requested = []
    client._perform_operation = lambda device, operation, poll_seconds: (
        requested.append((device["id"], operation, poll_seconds))
        or {"accepted": True, "operation": {"result": "success"}}
    )

    result = client.locate("Primary Galaxy", poll_seconds=180)

    assert requested == [("device-1", "LOCATION", 180)]
    assert result["fresh_location_obtained"] is True
    assert result["latitude"] == 11.0
    assert result["timezone"] == "UTC"
    assert result["last_update"].endswith("+00:00")
    assert "id" not in result["device"]
    assert result["active_operation"]["operation"]["result"] == "success"


def test_track_uses_start_and_stop_operation(monkeypatch):
    for enabled, expected in [(True, "TRACK_LOCATION_START"), (False, "TRACK_LOCATION_STOP")]:
        client = client_with_devices([phone()])
        web = FakeWeb(
            [
                FakeResponse(payload={"resultCode": "00", "reqId": "track-1"}),
                FakeResponse(
                    payload={
                        "operation": [
                            {
                                "oprnType": expected,
                                "oprnStsCd": "2100" if enabled else "2800",
                                "oprnResultCode": "1200",
                                "reqId": "track-1",
                            }
                        ]
                    }
                ),
            ]
        )
        client._web_session = lambda current_web=web: (current_web, "csrf")
        monkeypatch.setattr("samsung_find.api.time.sleep", lambda _seconds: None)

        result = client.track("Primary Galaxy", enabled=enabled, poll_seconds=1)

        assert web.calls[0][1]["json"]["operation"] == expected
        assert result["accepted"] is True


def test_private_operation_helper_rejects_destructive_operations():
    client = client_with_devices([phone()])
    client._web_session = lambda: pytest.fail("network session must not be opened")

    with pytest.raises(SamsungAuthError, match="not allowed"):
        client._perform_operation(phone(), "WIPE", poll_seconds=0)


def test_private_operation_helper_rejects_operation_string_subclasses():
    class DeceptiveOperation(str):
        def __hash__(self):
            return hash("RING")

        def __eq__(self, other):
            return other == "RING"

    client = client_with_devices([phone()])
    client._web_session = lambda: pytest.fail("network session must not be opened")

    with pytest.raises(SamsungAuthError, match="plain string"):
        client._perform_operation(
            phone(),
            DeceptiveOperation("WIPE"),
            ring_status="start",
            poll_seconds=0,
        )


def test_private_operation_helper_has_no_generic_payload_surface():
    client = client_with_devices([phone()])
    client._web_session = lambda: pytest.fail("network session must not be opened")

    operation_helper = cast(Any, client._perform_operation)
    with pytest.raises(TypeError, match="unexpected keyword argument 'payload'"):
        operation_helper(
            phone(),
            "RING",
            payload={"operation": "WIPE"},
            poll_seconds=0,
        )


def test_private_operation_helper_rejects_ring_parameters_for_other_operations():
    client = client_with_devices([phone()])
    client._web_session = lambda: pytest.fail("network session must not be opened")

    with pytest.raises(SamsungAuthError, match="only allowed for RING"):
        client._perform_operation(
            phone(),
            "LOCATION",
            ring_status="start",
            poll_seconds=0,
        )


def test_generic_installed_app_execute_is_removed():
    assert not hasattr(SamsungFindClient, "_execute")
