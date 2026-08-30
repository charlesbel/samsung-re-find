from __future__ import annotations

import html
import math
import time
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .auth import FIND, IOT, SamsungAuth, SamsungAuthError
from .constants import SMARTTHINGS_APP_VERSION, SMARTTHINGS_USER_AGENT

_ALLOWED_OPERATIONS = frozenset(
    {
        "CHECK_CONNECTION",
        "LOCATION",
        "RING",
        "TRACK_LOCATION_START",
        "TRACK_LOCATION_STOP",
    }
)


class SamsungFindClient:
    def __init__(
        self,
        auth: SamsungAuth,
        *,
        country: str = "US",
        language: str = "en",
        timezone: str = "UTC",
    ):
        self.auth = auth
        self.country = country.upper()
        self.language = language
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {timezone}") from exc
        self.http = httpx.Client(timeout=30.0, follow_redirects=True)
        self._correlation = str(uuid.uuid4())
        self._user_uuid: str | None = None
        self._installed_app_id: str | None = None

    def __enter__(self) -> SamsungFindClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @classmethod
    def from_config(cls, config: Any = None) -> SamsungFindClient:
        from .config import FindConfig

        cfg = config or FindConfig()
        auth = SamsungAuth(
            state_path=str(cfg.state_path),
            pending_path=str(cfg.pending_path),
            master_path=cfg.master_state_path,
            timeout=cfg.timeout_s,
        )
        return cls(
            auth,
            country=cfg.country,
            language=cfg.language,
            timezone=cfg.timezone,
        )

    def close(self) -> None:
        self.http.close()

    def _headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        token = self.auth.access_token(IOT, force_refresh=force_refresh)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.smartthings+json;v=1",
            "Accept-Language": f"{self.language}-{self.country}",
            "User-Agent": SMARTTHINGS_USER_AGENT,
            "X-St-Client-Appversion": SMARTTHINGS_APP_VERSION,
            "X-St-Client-Devicemodel": "Google Pixel 8 Pro",
            "X-St-Client-Os": "Android 14",
            "X-St-Correlation": self._correlation,
        }

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        from .transport import validate_smartthings_url

        valid_url = validate_smartthings_url(str(url))
        headers = kwargs.pop("headers", None) or self._headers()
        response = self.http.request(method, valid_url, headers=headers, **kwargs)
        if response.status_code in (401, 403) and method.upper() == "GET":
            response = self.http.request(method, valid_url, headers=self._headers(force_refresh=True), **kwargs)
        if not response.is_success:
            raise SamsungAuthError(f"SmartThings request failed with HTTP {response.status_code}")
        return response

    def verify_find_token(self) -> bool:
        state = self.auth.state()
        auth_server = state["auth_server_url"].removeprefix("https://").removeprefix("http://")
        headers = {
            "X-Sec-Sa-Userid": state["user_id"],
            "X-Sec-Sa-Countrycode": "FRA" if self.country == "FR" else self.country,
            "X-Sec-Sa-Authserverurl": auth_server,
            "X-Sec-Sa-Authtoken": self.auth.access_token(FIND),
            "X-Sec-Tab-Name": "DEVICES",
            "Accept": "application/json",
        }
        url = f"https://api.samsungfind.com/users/{state['user_id']}/key"
        response = self.http.get(url, headers=headers)
        if response.status_code in (401, 403):
            headers["X-Sec-Sa-Authtoken"] = self.auth.access_token(FIND, force_refresh=True)
            response = self.http.get(url, headers=headers)
        return response.status_code == 200

    def _ensure_user_uuid(self) -> str:
        if self._user_uuid:
            return self._user_uuid
        data = self._request("GET", "https://auth.api.smartthings.com/users/me").json()
        value = data.get("uuid")
        if not value:
            raise SamsungAuthError("SmartThings user response omitted uuid")
        self._user_uuid = str(value)
        return self._user_uuid

    def _ensure_installed_app(self) -> str:
        if self._installed_app_id:
            return self._installed_app_id
        from .transport import validate_smartthings_url

        user_uuid = self._ensure_user_uuid()
        initial_url = "https://api.smartthings.com/installedapps?allowed=true"
        url: str | None = initial_url
        candidates: list[dict[str, Any]] = []
        while url:
            valid_url = validate_smartthings_url(url, base_url=initial_url)
            data = self._request("GET", valid_url).json()
            candidates.extend(data.get("items", []))
            next_link = (data.get("_links") or {}).get("next") or {}
            url = next_link.get("href")
        plugin = "com.samsung.android.plugin.fme"
        selected = next(
            (
                item
                for item in candidates
                if (item.get("ui") or {}).get("pluginId") == plugin
                and (item.get("owner") or {}).get("ownerId") == user_uuid
            ),
            None,
        ) or next(
            (item for item in candidates if (item.get("ui") or {}).get("pluginId") == plugin),
            None,
        )
        if not selected or not selected.get("installedAppId"):
            raise SamsungAuthError("Samsung Find installed app was not found in SmartThings")
        self._installed_app_id = str(selected["installedAppId"])
        return self._installed_app_id

    def _web_session(self) -> tuple[httpx.Client, str]:
        def create(force: bool) -> tuple[httpx.Client, str | None]:
            cookie = self.auth.web_session_cookie(force_refresh=force)
            web = httpx.Client(timeout=30.0, follow_redirects=True, cookies={"JSESSIONID": cookie})
            response = web.get("https://smartthingsfind.samsung.com/chkLogin.do")
            return web, response.headers.get("_csrf") if response.status_code == 200 else None

        web, csrf = create(False)
        if not csrf:
            web.close()
            web, csrf = create(True)
        if not csrf:
            web.close()
            raise SamsungAuthError("Unable to establish a SmartThings Find web session")
        return web, csrf

    def devices(self) -> list[dict[str, Any]]:
        web, csrf = self._web_session()
        try:
            response = web.post(
                "https://smartthingsfind.samsung.com/device/getDeviceList.do",
                params={"_csrf": csrf},
                data={},
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                raise SamsungAuthError(f"Samsung web device list failed with HTTP {response.status_code}")
            items = response.json().get("deviceList", [])
        finally:
            web.close()
        result = []
        for item in items:
            device_id = item.get("dvceID")
            if not device_id:
                continue
            name = html.unescape(html.unescape(str(item.get("modelName") or device_id)))
            result.append(
                {
                    "id": str(device_id),
                    "name": name,
                    "model": item.get("modelID"),
                    "location_type": item.get("deviceTypeCode"),
                    "user_id": item.get("usrId"),
                    "raw": item,
                }
            )
        return result

    def resolve_device(self, query: str) -> dict[str, Any]:
        devices = self.devices()
        needle = query.casefold()
        exact = [
            device
            for device in devices
            if needle
            in {
                str(device.get("id", "")).casefold(),
                str(device.get("model", "")).casefold(),
                str(device.get("name", "")).casefold(),
            }
        ]
        matches = exact or [
            device
            for device in devices
            if needle in str(device.get("name", "")).casefold() or needle in str(device.get("model", "")).casefold()
        ]
        if not matches:
            names = ", ".join(str(device.get("name")) for device in devices)
            raise SamsungAuthError(f"No device matched {query!r}. Available: {names}")
        if len(matches) > 1:
            names = ", ".join(str(device.get("name")) for device in matches)
            raise SamsungAuthError(f"Device query is ambiguous: {names}")
        return matches[0]

    def capabilities(self, query: str) -> dict[str, Any]:
        device = self.resolve_device(query)
        device_type = str((device.get("raw") or {}).get("deviceType") or "").upper()
        ring_types = {"PHONE", "TAB", "WATCH", "BUDS", "TAG", "VR"}
        track_types = {"PHONE", "TAB"}
        return {
            "device": {key: device.get(key) for key in ("name", "model", "location_type")},
            "passive_location": True,
            "active_location": True,
            "connection_check": True,
            "battery_status": True,
            "ring": device_type in ring_types,
            "continuous_tracking": device_type in track_types,
            "remote_lock": "discovered_not_exposed",
            "remote_wipe": "discovered_not_exposed",
        }

    @staticmethod
    def _operation_result_label(operation_type: Any, status: Any, result: Any) -> str:
        if str(operation_type) == "TRACK_LOCATION_START" and str(status) == "2100":
            return "success"
        if str(status) == "2800" and str(result) == "1200":
            return "success"
        if str(status) in {"1000", "2100"}:
            return "in_progress"
        if str(status) in {"1900", "2900", "01", "02"}:
            return "failed"
        return "unknown"

    def _sanitize_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        battery = operation.get("battery")
        try:
            battery = int(battery) if battery is not None else None
        except (TypeError, ValueError):
            battery = None
        result = {
            "type": operation.get("oprnType"),
            "status_code": operation.get("oprnStsCd"),
            "result_code": operation.get("oprnResultCode"),
            "result": self._operation_result_label(
                operation.get("oprnType"), operation.get("oprnStsCd"), operation.get("oprnResultCode")
            ),
            "battery_percent": battery,
        }
        for source, destination in (("oprnCrtDate", "created_at"), ("oprnDoneDate", "completed_at")):
            value = operation.get(source)
            if value:
                try:
                    timestamp = datetime.strptime(str(value), "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("UTC"))
                    result[destination] = timestamp.astimezone(self.timezone).isoformat()
                except ValueError:
                    pass
        return result

    def _perform_operation(
        self,
        device: dict[str, Any],
        operation: str,
        *,
        ring_status: str | None = None,
        ring_message: str | None = None,
        poll_seconds: int = 40,
    ) -> dict[str, Any]:
        if type(operation) is not str:
            raise SamsungAuthError("Samsung operation must be a plain string")
        if operation not in _ALLOWED_OPERATIONS:
            raise SamsungAuthError(f"Samsung operation {operation!r} is not allowed")
        if ring_status is not None and type(ring_status) is not str:
            raise SamsungAuthError("ring_status must be a plain string")
        if ring_message is not None and type(ring_message) is not str:
            raise SamsungAuthError("ring_message must be a plain string")
        if operation == "RING":
            if ring_status not in {"start", "stop"}:
                raise SamsungAuthError("RING requires ring_status 'start' or 'stop'")
        elif ring_status is not None or ring_message is not None:
            raise SamsungAuthError("Ring parameters are only allowed for RING")
        request_payload = {
            "dvceId": device["id"],
            "operation": operation,
            "usrId": device.get("user_id"),
        }
        if operation == "RING":
            request_payload["status"] = ring_status
            if ring_message:
                request_payload["lockMessage"] = ring_message
        web, csrf = self._web_session()
        try:
            response = web.post(
                "https://smartthingsfind.samsung.com/dm/addOperation.do",
                params={"_csrf": csrf},
                json=request_payload,
            )
            if response.status_code != 200:
                raise SamsungAuthError(f"Samsung operation {operation} failed with HTTP {response.status_code}")
            accepted_data = response.json()
            accepted = accepted_data.get("resultCode") == "00"
            if not accepted:
                raise SamsungAuthError(f"Samsung rejected operation {operation} ({accepted_data.get('resultCode')})")
            request_id = accepted_data.get("reqId")
            if not request_id:
                raise SamsungAuthError(f"Samsung accepted operation {operation} but omitted request id")
            deadline = time.monotonic() + max(0, poll_seconds)
            latest = None
            while time.monotonic() <= deadline:
                result_response = web.post(
                    "https://smartthingsfind.samsung.com/dm/getOperationResult.do",
                    params={"_csrf": csrf},
                    json={
                        "dvceId": device["id"],
                        "operation": [operation],
                        "userId": device.get("user_id"),
                    },
                )
                if result_response.status_code == 200:
                    operations = result_response.json().get("operation", [])
                    candidates = [entry for entry in operations if entry.get("oprnType") == operation]
                    candidates = [entry for entry in candidates if str(entry.get("reqId")) == str(request_id)]
                    if candidates:
                        latest = self._sanitize_operation(candidates[-1])
                        if latest["result"] in {"success", "failed"}:
                            break
                if time.monotonic() >= deadline:
                    break
                time.sleep(min(3, max(0, poll_seconds)))
            return {
                "device": {key: device.get(key) for key in ("name", "model", "location_type")},
                "requested_operation": operation,
                "accepted": True,
                "operation": latest,
            }
        finally:
            web.close()

    def check_connection(self, query: str, *, poll_seconds: int = 40) -> dict[str, Any]:
        return self._perform_operation(self.resolve_device(query), "CHECK_CONNECTION", poll_seconds=poll_seconds)

    def ring(
        self,
        query: str,
        *,
        status: str = "start",
        message: str | None = None,
        poll_seconds: int = 40,
    ) -> dict[str, Any]:
        if status not in {"start", "stop"}:
            raise ValueError("ring status must be 'start' or 'stop'")
        device = self.resolve_device(query)
        if not self.capabilities(query)["ring"]:
            raise SamsungAuthError(f"Ringing is not exposed for {device.get('name')}")
        return self._perform_operation(
            device,
            "RING",
            ring_status=status,
            ring_message=message,
            poll_seconds=poll_seconds,
        )

    def track(self, query: str, *, enabled: bool, poll_seconds: int = 30) -> dict[str, Any]:
        device = self.resolve_device(query)
        if not self.capabilities(query)["continuous_tracking"]:
            raise SamsungAuthError(f"Continuous tracking is not exposed for {device.get('name')}")
        operation = "TRACK_LOCATION_START" if enabled else "TRACK_LOCATION_STOP"
        return self._perform_operation(device, operation, poll_seconds=poll_seconds)

    def locate(self, query: str, *, active: bool = True, poll_seconds: int = 180) -> dict[str, Any]:
        device = self.resolve_device(query)
        web, csrf = self._web_session()
        try:
            baseline = self._web_location(web, csrf, device)
        finally:
            web.close()

        location = baseline
        active_operation = None
        fresh_location_obtained = False
        if active:
            active_operation = self._perform_operation(device, "LOCATION", poll_seconds=poll_seconds)
            web, csrf = self._web_session()
            try:
                candidate = self._web_location(web, csrf, device)
            finally:
                web.close()
            if candidate:
                location = candidate
                fresh_location_obtained = baseline is None or candidate["timestamp"] > baseline["timestamp"]

        if not location:
            raise SamsungAuthError("Samsung returned no usable coordinates for this device")
        timestamp = location["timestamp"]
        latitude, longitude = location["latitude"], location["longitude"]
        return {
            "device": {key: device.get(key) for key in ("name", "model", "location_type")},
            "latitude": latitude,
            "longitude": longitude,
            "accuracy_m": location.get("accuracy_m"),
            "last_update": datetime.fromtimestamp(timestamp, tz=self.timezone).isoformat(),
            "timezone": str(self.timezone),
            "age_seconds": max(0, int(time.time() - timestamp)),
            "battery": location.get("battery"),
            "operation": location.get("operation"),
            "active_refresh_requested": bool(active_operation and active_operation.get("accepted")),
            "active_operation": active_operation,
            "fresh_location_obtained": fresh_location_obtained,
            "maps_url": f"https://www.google.com/maps?q={latitude},{longitude}",
        }

    @staticmethod
    def _web_location(web: httpx.Client, csrf: str, device: dict[str, Any]) -> dict[str, Any] | None:
        response = web.post(
            "https://smartthingsfind.samsung.com/device/setLastSelect.do",
            params={"_csrf": csrf},
            json={"dvceId": device["id"], "removeDevice": []},
            headers={"Accept": "application/json"},
        )
        if response.status_code != 200:
            return None
        best = None
        for operation in response.json().get("operation", []):
            if operation.get("oprnType") not in {"LOCATION", "LASTLOC", "OFFLINE_LOC"}:
                continue
            source = operation
            if "latitude" not in source and isinstance(operation.get("encLocation"), dict):
                source = operation["encLocation"]
                if source.get("encrypted"):
                    continue
            if source.get("latitude") is None or source.get("longitude") is None:
                continue
            gps_date = (operation.get("extra") or {}).get("gpsUtcDt") or source.get("gpsUtcDt")
            try:
                timestamp = datetime.strptime(str(gps_date), "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("UTC")).timestamp()
                latitude, longitude = float(source["latitude"]), float(source["longitude"])
            except (TypeError, ValueError):
                continue
            accuracy = None
            with suppress(TypeError, ValueError):
                accuracy = round(
                    math.hypot(
                        float(source.get("horizontalUncertainty")),
                        float(source.get("verticalUncertainty")),
                    ),
                    1,
                )
            candidate = {
                "timestamp": timestamp,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy_m": accuracy,
                "battery": operation.get("battery") or source.get("battery"),
                "operation": operation.get("oprnType"),
            }
            if best is None or candidate["timestamp"] > best["timestamp"]:
                best = candidate
        return best
