from __future__ import annotations

import secrets
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .capture_redirect import is_expected_redirect_uri
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
from .credentials import (
    ALLOWED_FIND_IOT_KEYS,
    ALLOWED_WEB_KEYS,
    MasterStateStore,
    project_legacy_derived,
    resolve_find_state_path,
    resolve_legacy_find_state_path,
    resolve_pending_path,
    validate_auth_server_url,
    validate_derived_state,
)
from .crypto import code_challenge, decrypt_auth_value, encrypt_svc_param, random_urlsafe
from .exceptions import AuthError, SecurityError
from .storage import atomic_write_json, locked, read_json

# Backward-compatibility alias
SamsungAuthError = AuthError


@dataclass(frozen=True)
class TokenKind:
    name: str
    client_id: str
    scope: str


FIND = TokenKind("find", FIND_CLIENT_ID, FIND_SCOPE)
IOT = TokenKind("iot", IOT_CLIENT_ID, IOT_SCOPE)


class SamsungAuth:
    def __init__(
        self,
        state_path: str | Path | None = None,
        pending_path: str | Path | None = None,
        *,
        master_path: str | Path | None = None,
        legacy_state_path: str | Path | None = None,
        timeout: float = 30.0,
    ):
        self.state_path = resolve_find_state_path(state_path)
        self.legacy_state_path = resolve_legacy_find_state_path(legacy_state_path or state_path)
        self.pending_path = resolve_pending_path(pending_path, master_path)
        self.master_store = MasterStateStore(
            master_path=master_path,
            canonical_state_path=self.state_path,
            legacy_path=self.legacy_state_path,
        )
        self.http = httpx.Client(timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        self.http.close()

    def _secret_post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a secret-bearing POST exactly once and reject every redirect."""
        response = self.http.post(url, follow_redirects=False, **kwargs)
        if 300 <= response.status_code < 400:
            raise SecurityError("Authentication redirect on secret-bearing POST is forbidden")
        return response

    def _authenticated_get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send an authenticated/query-secret GET once and reject redirects."""
        response = self.http.get(url, follow_redirects=False, **kwargs)
        if 300 <= response.status_code < 400:
            raise SecurityError("Authentication redirect on authenticated GET is forbidden")
        return response

    def __enter__(self) -> SamsungAuth:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _save_derived_state(self, state: dict[str, Any]) -> None:
        """Validate and atomically write canonical derived state."""
        validate_derived_state(state)
        atomic_write_json(self.state_path, state)

    def master_summary(self) -> dict[str, str | None]:
        """Return narrow non-secret master fields (auth_server_url, user_id, login_id) for API dispatch."""
        master = self.master_store.load(allow_legacy_fallback=True)
        if not master:
            return {"auth_server_url": None, "user_id": None, "login_id": None}
        return {
            "auth_server_url": master.identity.auth_server_url,
            "user_id": master.account.user_id,
            "login_id": master.account.login_id,
        }

    def start(self, country: str = "us", locale: str = "en-US") -> str:
        response = self._authenticated_get(ENTRY_POINT_URL)
        self._raise(response, "entry point")
        entry = response.json()
        device_id = secrets.token_hex(16)

        # Transiently obtain device_id from master or legacy without copying to derived state
        master = self.master_store.load(allow_legacy_fallback=True)
        if master and master.installation.physical_address:
            device_id = master.installation.physical_address

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
            raise AuthError("Pending Samsung authentication has expired")
        if not is_expected_redirect_uri(redirect_uri):
            raise AuthError("Samsung redirect does not match the configured callback target")
        parsed = urllib.parse.urlparse(redirect_uri)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.fragment:
            params.update(urllib.parse.parse_qs(parsed.fragment))

        def one(name: str) -> str:
            return params.get(name, [""])[0]

        encrypted_state = one("state")
        if not encrypted_state:
            raise AuthError("Redirect is missing encrypted state")
        try:
            response_key = decrypt_auth_value(encrypted_state, pending["state"])
            auth_server = decrypt_auth_value(one("auth_server_url"), response_key)
            code = decrypt_auth_value(one("code"), response_key)
            login_id = decrypt_auth_value(one("retValue"), response_key)
        except Exception as exc:
            raise AuthError("Unable to decrypt Samsung redirect") from exc
        auth_server = self._trusted_auth_server_url(auth_server)

        response = self._secret_post(
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
            raise AuthError("Samsung response omitted master user token or user id")

        # Save to neutral master store v1
        master_state = self.master_store.save(
            login_id=login_id,
            user_id=user_id,
            physical_address=pending["device_id"],
            auth_server_url=auth_server,
            userauth_token=userauth_token,
        )

        find_tok = self._issue_token(
            FIND,
            userauth_token=userauth_token,
            auth_server_url=auth_server,
            device_id=pending["device_id"],
            login_id=login_id,
        )
        iot_tok = self._issue_token(
            IOT,
            userauth_token=userauth_token,
            auth_server_url=auth_server,
            device_id=pending["device_id"],
            login_id=login_id,
        )

        # Write clean derived state ONLY (no master fields!)
        derived_state: dict[str, Any] = {
            "schema": 1,
            "master_generation": master_state.generation,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "find": find_tok,
            "iot": iot_tok,
        }
        with locked(self.state_path):
            self._save_derived_state(derived_state)
        Path(self.pending_path).expanduser().unlink(missing_ok=True)
        return self.public_status()

    def account_status(self) -> dict[str, bool | int]:
        """Return non-secret readiness for the neutral shared master only."""
        master = self.master_store.load(allow_legacy_fallback=True)
        return {
            "authenticated": bool(master and master.identity.userauth_token),
            "user_id_present": bool(master and master.account.user_id),
            "device_id_present": bool(master and master.installation.physical_address),
            "schema_version": 1,
        }

    def public_status(self) -> dict[str, Any]:
        status = self.account_status()
        derived = self._load_state_safe()
        if not derived and not self.state_path.exists() and self.legacy_state_path.exists():
            derived = self._load_legacy_safe()

        return {
            **status,
            "find_token_present": bool((derived.get("find") or {}).get("access_token")),
            "iot_token_present": bool((derived.get("iot") or {}).get("access_token")),
        }

    def _load_state_safe(self) -> dict[str, Any]:
        try:
            return read_json(self.state_path, required=False)
        except Exception:
            return {}

    def _load_legacy_safe(self) -> dict[str, Any]:
        try:
            return project_legacy_derived(read_json(self.legacy_state_path, required=False))
        except Exception:
            return {}

    @staticmethod
    def _empty_derived_state(*, generation: str | None = None, created_at: Any = None) -> dict[str, Any]:
        """Build a credential-free derived state at an account-generation boundary."""
        now = int(time.time())
        clean: dict[str, Any] = {
            "schema": 1,
            "created_at": created_at if type(created_at) in (int, float) else now,
            "updated_at": now,
        }
        if generation is not None:
            clean["master_generation"] = generation
        return clean

    def _reconcile_derived_generation(self, state: dict[str, Any], master: Any) -> tuple[dict[str, Any], bool]:
        """Clear credentials unless derived state belongs to the validated current master."""
        generation = master.generation if master else None
        if master and state.get("master_generation") == generation:
            validate_derived_state(state)
            return state, True

        # Do not inspect or validate credentials across an unknown account
        # boundary; discard the entire derived payload first.
        clean = self._empty_derived_state(
            generation=generation,
            created_at=state.get("created_at"),
        )
        self._save_derived_state(clean)
        return clean, False

    def access_token(self, kind: TokenKind, *, force_refresh: bool = False) -> str:
        with locked(self.state_path):
            # The master is the account boundary. Validate it before considering
            # any cached access/refresh token from derived state.
            master = self.master_store.load(allow_legacy_fallback=False)
            state = read_json(self.state_path, required=False)
            state, generation_matches = self._reconcile_derived_generation(state, master)
            if not master or not master.identity.userauth_token:
                raise AuthError("Authentication required: no master token found")

            token = state.get(kind.name) or {}
            expiry = float(token.get("expires_at", 0))
            if generation_matches and not force_refresh and token.get("access_token") and expiry > time.time() + 120:
                return str(token["access_token"])

            new_token = self._refresh_or_reissue(
                token,
                kind,
                userauth_token=master.identity.userauth_token,
                auth_server_url=master.identity.auth_server_url,
                device_id=master.installation.physical_address,
                login_id=master.account.login_id,
            )
            clean_state: dict[str, Any] = {
                "schema": 1,
                "master_generation": master.generation,
                "created_at": state.get("created_at", int(time.time())),
                "updated_at": int(time.time()),
            }
            if "find" in state and isinstance(state["find"], dict):
                clean_state["find"] = {k: v for k, v in state["find"].items() if k in ALLOWED_FIND_IOT_KEYS}
            if "iot" in state and isinstance(state["iot"], dict):
                clean_state["iot"] = {k: v for k, v in state["iot"].items() if k in ALLOWED_FIND_IOT_KEYS}
            if "web" in state and isinstance(state["web"], dict):
                clean_state["web"] = {k: v for k, v in state["web"].items() if k in ALLOWED_WEB_KEYS}
            clean_state[kind.name] = new_token
            self._save_derived_state(clean_state)
            return str(new_token["access_token"])

    def state(self) -> dict[str, Any]:
        """Return derived state only, projecting legacy fallback safely without master fields."""
        if self.state_path.exists():
            return validate_derived_state(read_json(self.state_path))
        if self.legacy_state_path.exists():
            return project_legacy_derived(read_json(self.legacy_state_path))
        return {}

    def web_session_cookie(self, *, force_refresh: bool = False) -> str:
        """Return a valid SmartThings Find web JSESSIONID."""
        with locked(self.state_path):
            # Never validate or return a cookie until the current master account
            # and its generation have been loaded and checked.
            master = self.master_store.load(allow_legacy_fallback=False)
            state = read_json(self.state_path, required=False)
            state, generation_matches = self._reconcile_derived_generation(state, master)
            if not master or not master.identity.userauth_token:
                raise AuthError("Authentication required: no master token found")

            current = (state.get("web") or {}).get("jsessionid")
            if generation_matches and current and not force_refresh and self._validate_web_cookie(str(current)):
                return str(current)

            params = {
                "response_type": "code",
                "serviceType": "M",
                "client_id": WEB_FIND_CLIENT_ID,
                "childAccountSupported": "Y",
                "userauth_token": master.identity.userauth_token,
                "physical_address_text": master.installation.physical_address,
                "scope": IOT_SCOPE,
                "login_id": master.account.login_id,
            }
            response = self._authenticated_get(
                f"{master.identity.auth_server_url}/auth/oauth2/v2/authorize", params=params
            )
            self._raise(response, "web Find authorization")
            auth_data = response.json()
            code = auth_data.get("code")
            if not code and auth_data.get("privacyAccepted") == "N":
                params.pop("login_id", None)
                response = self._authenticated_get(
                    f"{master.identity.auth_server_url}/auth/oauth2/v2/authorize", params=params
                )
                self._raise(response, "web Find authorization without login_id")
                auth_data = response.json()
                code = auth_data.get("code")
            if not code:
                raise AuthError("Samsung omitted the web Find authorization code")

            auth_host = urllib.parse.urlparse(master.identity.auth_server_url).netloc
            with httpx.Client(timeout=30.0, follow_redirects=False) as web:
                response = web.get(
                    "https://smartthingsfind.samsung.com/getState.do",
                    params={"payload": "hound"},
                )
                self._raise(response, "web Find state bootstrap")
                login_state = response.json().get("state")
                if not login_state:
                    raise AuthError("Samsung omitted the web Find login state")
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
                    raise AuthError("Samsung did not issue a web Find session cookie")
                jsessionid = cookies[-1]
            if not self._validate_web_cookie(jsessionid):
                raise AuthError("Samsung issued a web Find cookie that failed validation")

            clean_state: dict[str, Any] = {
                "schema": 1,
                "master_generation": master.generation,
                "created_at": state.get("created_at", int(time.time())),
                "updated_at": int(time.time()),
            }
            if "find" in state and isinstance(state["find"], dict):
                clean_state["find"] = {k: v for k, v in state["find"].items() if k in ALLOWED_FIND_IOT_KEYS}
            if "iot" in state and isinstance(state["iot"], dict):
                clean_state["iot"] = {k: v for k, v in state["iot"].items() if k in ALLOWED_FIND_IOT_KEYS}
            clean_state["web"] = {"jsessionid": jsessionid, "updated_at": int(time.time())}
            self._save_derived_state(clean_state)
            return jsessionid

    @staticmethod
    def _validate_web_cookie(jsessionid: str) -> bool:
        if not jsessionid or not isinstance(jsessionid, str) or not jsessionid.strip():
            return False
        try:
            with httpx.Client(
                timeout=30.0,
                follow_redirects=False,
                cookies={"JSESSIONID": jsessionid.strip()},
            ) as web:
                response = web.get("https://smartthingsfind.samsung.com/chkLogin.do")
                return response.status_code == 200 and bool(response.headers.get("_csrf"))
        except Exception:
            return False

    def _refresh_or_reissue(
        self,
        state_or_token: dict[str, Any],
        kind: TokenKind,
        *,
        userauth_token: str | None = None,
        auth_server_url: str | None = None,
        device_id: str | None = None,
        login_id: str | None = None,
    ) -> dict[str, Any]:
        if kind.name in state_or_token and isinstance(state_or_token[kind.name], dict):
            token = state_or_token[kind.name]
        else:
            token = state_or_token

        auth_server = auth_server_url or state_or_token.get("auth_server_url") or ""
        userauth = userauth_token or state_or_token.get("userauth_token") or ""
        dev_id = device_id or state_or_token.get("device_id") or ""
        lgn_id = login_id or state_or_token.get("login_id") or ""

        refresh = token.get("refresh_token")
        if refresh and auth_server:
            response = self._secret_post(
                f"{auth_server}/auth/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": kind.client_id,
                    "refresh_token": refresh,
                },
            )
            if response.status_code == 200:
                return self._normalize_token(response.json())

        try:
            return self._issue_token(
                kind,
                userauth_token=userauth,
                auth_server_url=auth_server,
                device_id=dev_id,
                login_id=lgn_id,
            )
        except TypeError:
            return self._issue_token(state_or_token, kind)

    def _issue_token(
        self,
        kind_or_state: Any,
        kind: TokenKind | None = None,
        *,
        userauth_token: str | None = None,
        auth_server_url: str | None = None,
        device_id: str | None = None,
        login_id: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(kind_or_state, TokenKind):
            actual_kind = kind_or_state
            state_dict: dict[str, Any] = {}
        else:
            state_dict = kind_or_state
            actual_kind = kind  # type: ignore

        userauth = userauth_token or state_dict.get("userauth_token") or ""
        auth_server = auth_server_url or state_dict.get("auth_server_url") or ""
        dev_id = device_id or state_dict.get("device_id") or ""
        lgn_id = login_id or state_dict.get("login_id") or ""

        verifier = random_urlsafe(32)[:43]
        params = {
            "response_type": "code",
            "serviceType": "M",
            "client_id": actual_kind.client_id,
            "code_challenge_method": "S256",
            "childAccountSupported": "Y",
            "userauth_token": userauth,
            "code_challenge": code_challenge(verifier),
            "physical_address_text": dev_id,
            "scope": actual_kind.scope,
            "login_id": lgn_id,
        }
        response = self._authenticated_get(f"{auth_server}/auth/oauth2/v2/authorize", params=params)
        self._raise(response, f"{actual_kind.name} authorization")
        auth_data = response.json()
        code = auth_data.get("code")
        if not code and auth_data.get("privacyAccepted") == "N":
            params.pop("login_id", None)
            response = self._authenticated_get(f"{auth_server}/auth/oauth2/v2/authorize", params=params)
            self._raise(response, f"{actual_kind.name} authorization without login_id")
            code = response.json().get("code")
        if not code:
            raise AuthError(f"Samsung omitted the {actual_kind.name} authorization code")
        response = self._secret_post(
            f"{auth_server}/auth/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": actual_kind.client_id,
                "code": code,
                "code_verifier": verifier,
                "physical_address_text": dev_id,
            },
        )
        self._raise(response, f"{actual_kind.name} token exchange")
        return self._normalize_token(response.json())

    @staticmethod
    def _trusted_auth_server_url(value: str) -> str:
        try:
            return validate_auth_server_url(value)
        except SecurityError as exc:
            raise AuthError("Samsung returned an untrusted authentication server") from exc

    @staticmethod
    def _normalize_token(token: dict[str, Any]) -> dict[str, Any]:
        if not token.get("access_token") or not token.get("refresh_token"):
            raise AuthError("Samsung token response is incomplete")
        normalized = dict(token)
        normalized["obtained_at"] = int(time.time())
        normalized["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600))
        return normalized

    @staticmethod
    def _raise(response: httpx.Response, step: str) -> None:
        if response.is_success:
            return
        raise AuthError(f"Samsung {step} failed with HTTP {response.status_code}")
