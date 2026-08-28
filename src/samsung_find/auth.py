from __future__ import annotations

import secrets
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .constants import (
    AUTH_CLIENT_ID,
    ENTRY_POINT_URL,
    FIND_CLIENT_ID,
    FIND_SCOPE,
    IOT_CLIENT_ID,
    IOT_SCOPE,
    REDIRECT_URI,
    WEB_FIND_CLIENT_ID,
)
from .crypto import code_challenge, decrypt_auth_value, encrypt_svc_param, random_urlsafe
from .storage import atomic_write_json, locked, read_json


class SamsungAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenKind:
    name: str
    client_id: str
    scope: str


FIND = TokenKind("find", FIND_CLIENT_ID, FIND_SCOPE)
IOT = TokenKind("iot", IOT_CLIENT_ID, IOT_SCOPE)


class SamsungAuth:
    def __init__(self, state_path: str, pending_path: str, *, timeout: float = 30.0):
        self.state_path = state_path
        self.pending_path = pending_path
        self.http = httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.http.close()

    def start(self, country: str = "us", locale: str = "en-US") -> str:
        response = self.http.get(ENTRY_POINT_URL)
        self._raise(response, "entry point")
        entry = response.json()
        device_id = secrets.token_hex(16)
        try:
            current = read_json(self.state_path, required=False)
            device_id = current.get("device_id") or device_id
        except (ValueError, OSError):
            pass

        state = random_urlsafe(15)[:20]
        verifier = random_urlsafe(32)[:43]
        payload = {
            "clientId": AUTH_CLIENT_ID,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
            "competitorDeviceYNFlag": "Y",
            "countryCode": country.lower(),
            "deviceInfo": "Google|com.android.chrome",
            "deviceModelID": "Pixel 8 Pro",
            "deviceName": "Google Pixel 8 Pro",
            "deviceOSVersion": "35",
            "devicePhysicalAddressText": f"ANID:{device_id}",
            "deviceType": "APP",
            "deviceUniqueID": device_id,
            "redirect_uri": REDIRECT_URI,
            "replaceableClientConnectYN": "N",
            "replaceableClientId": "",
            "replaceableDevicePhysicalAddressText": "",
            "responseEncryptionType": "1",
            "responseEncryptionYNFlag": "Y",
            "scope": "",
            "state": state,
            "svcIptLgnID": "",
            "iosYNFlag": "Y",
        }
        encrypted = encrypt_svc_param(payload, int(entry["chkDoNum"]), entry["pkiPublicKey"])
        pending = {
            "state": state,
            "code_verifier": verifier,
            "device_id": device_id,
            "created_at": int(time.time()),
        }
        with locked(self.pending_path):
            atomic_write_json(self.pending_path, pending)
        sign_in = entry["signInURI"]
        return f"{sign_in}?locale={urllib.parse.quote(locale)}&svcParam={encrypted}&mode=C"

    def complete(self, redirect_uri: str) -> dict[str, Any]:
        pending = read_json(self.pending_path)
        try:
            pending_age = time.time() - float(pending["created_at"])
        except (KeyError, TypeError, ValueError):
            pending_age = float("inf")
        if pending_age < -60 or pending_age > 900:
            Path(self.pending_path).expanduser().unlink(missing_ok=True)
            raise SamsungAuthError("Pending Samsung authentication has expired")
        parsed = urllib.parse.urlparse(redirect_uri)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.fragment:
            params.update(urllib.parse.parse_qs(parsed.fragment))

        def one(name: str) -> str:
            return params.get(name, [""])[0]

        encrypted_state = one("state")
        if not encrypted_state:
            raise SamsungAuthError("Redirect is missing encrypted state")
        try:
            response_key = decrypt_auth_value(encrypted_state, pending["state"])
            auth_server = decrypt_auth_value(one("auth_server_url"), response_key)
            code = decrypt_auth_value(one("code"), response_key)
            login_id = decrypt_auth_value(one("retValue"), response_key)
        except Exception as exc:
            raise SamsungAuthError("Unable to decrypt Samsung redirect") from exc
        auth_server = self._trusted_auth_server_url(auth_server)

        response = self.http.post(
            f"{auth_server}/auth/oauth2/authenticate",
            data={
                "grant_type": "authorization_code",
                "serviceType": "M",
                "client_id": AUTH_CLIENT_ID,
                "code": code,
                "code_verifier": pending["code_verifier"],
                "username": login_id,
                "physical_address_text": pending["device_id"],
            },
        )
        self._raise(response, "master authentication")
        master = response.json()
        userauth_token = master.get("userauth_token") or master.get("userAuthToken")
        user_id = master.get("userId") or master.get("user_id")
        if not userauth_token or not user_id:
            raise SamsungAuthError("Samsung response omitted master user token or user id")

        state: dict[str, Any] = {
            "schema": 1,
            "device_id": pending["device_id"],
            "auth_server_url": auth_server,
            "login_id": login_id,
            "user_id": user_id,
            "userauth_token": userauth_token,
            "created_at": int(time.time()),
        }
        state["find"] = self._issue_token(state, FIND)
        state["iot"] = self._issue_token(state, IOT)
        with locked(self.state_path):
            atomic_write_json(self.state_path, state)
        Path(self.pending_path).expanduser().unlink(missing_ok=True)
        return self.public_status(state)

    def public_status(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = state or read_json(self.state_path)
        return {
            "authenticated": bool(state.get("userauth_token")),
            "user_id_present": bool(state.get("user_id")),
            "device_id_present": bool(state.get("device_id")),
            "find_token_present": bool((state.get("find") or {}).get("access_token")),
            "iot_token_present": bool((state.get("iot") or {}).get("access_token")),
        }

    def access_token(self, kind: TokenKind, *, force_refresh: bool = False) -> str:
        with locked(self.state_path):
            state = read_json(self.state_path)
            token = state.get(kind.name) or {}
            expiry = float(token.get("expires_at", 0))
            if not force_refresh and token.get("access_token") and expiry > time.time() + 120:
                return str(token["access_token"])
            state[kind.name] = self._refresh_or_reissue(state, kind)
            atomic_write_json(self.state_path, state)
            return str(state[kind.name]["access_token"])

    def state(self) -> dict[str, Any]:
        return read_json(self.state_path)

    def web_session_cookie(self, *, force_refresh: bool = False) -> str:
        """Return a valid SmartThings Find web JSESSIONID.

        The web OAuth client does not use PKCE. Supplying a code challenge here
        creates a code that login.do cannot redeem, yielding a cookie that looks
        present but is unauthenticated. The login exchange must also preserve the
        server state and bootstrap cookie issued by getState.do.
        """
        with locked(self.state_path):
            state = read_json(self.state_path)
            current = (state.get("web") or {}).get("jsessionid")
            if current and not force_refresh and self._validate_web_cookie(str(current)):
                return str(current)

            params = {
                "response_type": "code",
                "serviceType": "M",
                "client_id": WEB_FIND_CLIENT_ID,
                "childAccountSupported": "Y",
                "userauth_token": state["userauth_token"],
                "physical_address_text": state["device_id"],
                "scope": IOT_SCOPE,
                "login_id": state["login_id"],
            }
            response = self.http.get(
                f"{state['auth_server_url']}/auth/oauth2/v2/authorize", params=params
            )
            self._raise(response, "web Find authorization")
            auth_data = response.json()
            code = auth_data.get("code")
            if not code and auth_data.get("privacyAccepted") == "N":
                params.pop("login_id", None)
                response = self.http.get(
                    f"{state['auth_server_url']}/auth/oauth2/v2/authorize", params=params
                )
                self._raise(response, "web Find authorization without login_id")
                auth_data = response.json()
                code = auth_data.get("code")
            if not code:
                raise SamsungAuthError("Samsung omitted the web Find authorization code")

            auth_host = urllib.parse.urlparse(state["auth_server_url"]).netloc
            with httpx.Client(timeout=30.0, follow_redirects=True) as web:
                response = web.get(
                    "https://smartthingsfind.samsung.com/getState.do",
                    params={"payload": "hound"},
                )
                self._raise(response, "web Find state bootstrap")
                login_state = response.json().get("state")
                if not login_state:
                    raise SamsungAuthError("Samsung omitted the web Find login state")
                response = web.get(
                    "https://smartthingsfind.samsung.com/login.do",
                    params={
                        "auth_server_url": auth_host,
                        "api_server_url": auth_host,
                        "code": code,
                        "code_expires_in": auth_data.get("code_expires_in", 300),
                        "state": login_state,
                    },
                )
                self._raise(response, "web Find session exchange")
                cookies = [cookie.value for cookie in web.cookies.jar if cookie.name == "JSESSIONID"]
                if not cookies:
                    raise SamsungAuthError("Samsung did not issue a web Find session cookie")
                jsessionid = cookies[-1]
            if not self._validate_web_cookie(jsessionid):
                raise SamsungAuthError("Samsung issued a web Find cookie that failed validation")
            state["web"] = {"jsessionid": jsessionid, "obtained_at": int(time.time())}
            atomic_write_json(self.state_path, state)
            return jsessionid

    @staticmethod
    def _validate_web_cookie(jsessionid: str) -> bool:
        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            cookies={"JSESSIONID": jsessionid},
        ) as web:
            response = web.get("https://smartthingsfind.samsung.com/chkLogin.do")
            return response.status_code == 200 and bool(response.headers.get("_csrf"))

    def _refresh_or_reissue(self, state: dict[str, Any], kind: TokenKind) -> dict[str, Any]:
        current = state.get(kind.name) or {}
        refresh = current.get("refresh_token")
        if refresh:
            response = self.http.post(
                f"{state['auth_server_url']}/auth/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": kind.client_id,
                    "refresh_token": refresh,
                },
            )
            if response.status_code == 200:
                return self._normalize_token(response.json())
        # This is the permanence layer: a dead/90-day refresh token is replaced
        # by a fresh authorization using the non-expiring userauth_token.
        return self._issue_token(state, kind)

    def _issue_token(self, state: dict[str, Any], kind: TokenKind) -> dict[str, Any]:
        verifier = random_urlsafe(32)[:43]
        params = {
            "response_type": "code",
            "serviceType": "M",
            "client_id": kind.client_id,
            "code_challenge_method": "S256",
            "childAccountSupported": "Y",
            "userauth_token": state["userauth_token"],
            "code_challenge": code_challenge(verifier),
            "physical_address_text": state["device_id"],
            "scope": kind.scope,
            "login_id": state["login_id"],
        }
        response = self.http.get(f"{state['auth_server_url']}/auth/oauth2/v2/authorize", params=params)
        self._raise(response, f"{kind.name} authorization")
        auth_data = response.json()
        code = auth_data.get("code")
        if not code and auth_data.get("privacyAccepted") == "N":
            params.pop("login_id", None)
            response = self.http.get(f"{state['auth_server_url']}/auth/oauth2/v2/authorize", params=params)
            self._raise(response, f"{kind.name} authorization without login_id")
            code = response.json().get("code")
        if not code:
            raise SamsungAuthError(f"Samsung omitted the {kind.name} authorization code")
        response = self.http.post(
            f"{state['auth_server_url']}/auth/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": kind.client_id,
                "code": code,
                "code_verifier": verifier,
                "physical_address_text": state["device_id"],
            },
        )
        self._raise(response, f"{kind.name} token exchange")
        return self._normalize_token(response.json())

    @staticmethod
    def _trusted_auth_server_url(value: str) -> str:
        parsed = urllib.parse.urlparse(value)
        hostname = (parsed.hostname or "").lower()
        trusted_host = (
            hostname == "account.samsung.com"
            or hostname == "samsungosp.com"
            or hostname.endswith(".samsungosp.com")
        )
        try:
            port = parsed.port
        except ValueError as exc:
            raise SamsungAuthError("Samsung returned an untrusted authentication server") from exc
        if (
            parsed.scheme != "https"
            or not trusted_host
            or parsed.username
            or parsed.password
            or port not in (None, 443)
            or parsed.path not in ("", "/")
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise SamsungAuthError("Samsung returned an untrusted authentication server")
        return f"https://{hostname}"

    @staticmethod
    def _normalize_token(token: dict[str, Any]) -> dict[str, Any]:
        if not token.get("access_token") or not token.get("refresh_token"):
            raise SamsungAuthError("Samsung token response is incomplete")
        normalized = dict(token)
        normalized["obtained_at"] = int(time.time())
        normalized["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600))
        return normalized

    @staticmethod
    def _raise(response: httpx.Response, step: str) -> None:
        if response.is_success:
            return
        # Deliberately do not include response bodies: Samsung may echo secrets.
        raise SamsungAuthError(f"Samsung {step} failed with HTTP {response.status_code}")
