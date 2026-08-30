"""Secure transport layer for SmartThings and Samsung APIs."""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from typing import Any

import httpx

from .constants import SMARTTHINGS_USER_AGENT
from .exceptions import AuthError, NetworkError, SecurityError

_ALLOWED_OPERATIONS = frozenset(
    {
        "CHECK_CONNECTION",
        "LOCATION",
        "RING",
        "TRACK_LOCATION_START",
        "TRACK_LOCATION_STOP",
    }
)

_PROTECTED_FIELDS = frozenset(
    {
        "requester",
        "requesterToken",
        "method",
        "uri",
        "user_uuid",
        "operation",
        "device_id",
        "oprnType",
    }
)

_TRUSTED_HOSTS = frozenset(
    {
        "api.smartthings.com",
        "auth.api.smartthings.com",
        "smartthingsfind.samsung.com",
        "api.samsungfind.com",
        "account.samsung.com",
        "samsungosp.com",
    }
)


def is_trusted_smartthings_host(hostname: str) -> bool:
    host = hostname.lower()
    if host in _TRUSTED_HOSTS:
        return True
    return host.endswith(".smartthings.com") or host.endswith(".samsungosp.com") or host.endswith(".samsungfind.com")


def validate_smartthings_url(url: str, base_url: str | None = None) -> str:
    """Validate that target URL is a safe HTTPS SmartThings destination."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        raise SecurityError(f"Invalid URL structure: {exc}") from exc

    if parsed.scheme != "https":
        raise SecurityError(f"Insecure scheme {parsed.scheme!r}: only HTTPS is allowed")

    hostname = (parsed.hostname or "").lower()
    if not hostname or not is_trusted_smartthings_host(hostname):
        raise SecurityError(f"Untrusted target host: {hostname or 'unknown'}")

    try:
        port = parsed.port
    except ValueError as exc:
        raise SecurityError("Invalid URL port") from exc

    if port not in (None, 443):
        raise SecurityError(f"Non-standard port {port} rejected on authenticated endpoint")

    if parsed.username or parsed.password:
        raise SecurityError("Userinfo is forbidden in authenticated request URLs")

    if base_url:
        base_parsed = urllib.parse.urlparse(base_url)
        base_host = (base_parsed.hostname or "").lower()
        if hostname != base_host:
            raise SecurityError(f"Hostile or untrusted pagination URL switches host from {base_host} to {hostname}")

    return url


class SmartThingsTransport:
    """Hardened HTTP transport enforcing destination allowlists and safe retries."""

    def __init__(
        self,
        token_getter: Callable[..., str],
        *,
        timeout: float = 30.0,
        language: str = "en",
        country: str = "US",
        http_client: httpx.Client | None = None,
    ):
        self._token_getter = token_getter
        self.language = language
        self.country = country
        self.http = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.http.close()

    def _headers(self, *, token: str | None = None, force_refresh: bool = False) -> dict[str, str]:
        if token:
            tok = token
        elif callable(self._token_getter):
            try:
                tok = self._token_getter(force_refresh=force_refresh)
            except TypeError:
                tok = self._token_getter()
        else:
            tok = ""
        return {
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.smartthings+json;v=1",
            "Accept-Language": f"{self.language}-{self.country}",
            "User-Agent": SMARTTHINGS_USER_AGENT,
        }

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        retry_auth: bool = True,
    ) -> httpx.Response:
        """Send an authenticated GET request with automatic retry on 401 (idempotent read)."""
        valid_url = validate_smartthings_url(url)
        headers = self._headers()
        try:
            response = self.http.get(valid_url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise NetworkError(f"SmartThings request failed: {exc}") from exc

        if response.status_code in (401, 403) and retry_auth:
            headers = self._headers(force_refresh=True)
            try:
                response = self.http.get(valid_url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise NetworkError(f"SmartThings retry failed: {exc}") from exc

        return response

    def execute_action(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        idempotent: bool = False,
    ) -> httpx.Response:
        """Execute an action (POST/PUT/DELETE).

        Non-idempotent actions are NOT automatically retried after 401/403 to prevent
        unintended duplicate state changes or side effects.
        """
        valid_url = validate_smartthings_url(url)
        headers = self._headers()

        try:
            response = self.http.post(valid_url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise NetworkError(f"Action execution failed: {exc}") from exc

        if response.status_code in (401, 403):
            if idempotent:
                headers = self._headers(force_refresh=True)
                try:
                    response = self.http.post(valid_url, headers=headers, json=payload)
                except httpx.HTTPError as exc:
                    raise NetworkError(f"Idempotent action retry failed: {exc}") from exc
            else:
                raise AuthError(
                    f"Authentication failure during action execution (HTTP {response.status_code}); "
                    "automatic retry disabled for non-idempotent action"
                )

        return response

    def paginate(
        self,
        initial_url: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Paginate a collection with strict same-host validation for each page link."""
        items: list[dict[str, Any]] = []
        current_url: str | None = initial_url
        current_params = params

        while current_url:
            valid_url = validate_smartthings_url(current_url, base_url=initial_url)
            response = self.get(valid_url, params=current_params)
            if response.status_code != 200:
                raise NetworkError(f"Pagination failed with HTTP {response.status_code}")

            data = response.json()
            if isinstance(data, dict):
                page_items = data.get("items") or []
                if isinstance(page_items, list):
                    items.extend(page_items)
                next_link = (data.get("_links") or {}).get("next") or {}
                next_href = next_link.get("href")
                if next_href:
                    current_url = str(next_href)
                    current_params = None
                else:
                    current_url = None
            elif isinstance(data, list):
                items.extend(data)
                current_url = None
            else:
                break

        return items

    @staticmethod
    def build_installed_app_payload(
        operation: str,
        device_id: str,
        user_uuid: str,
        override_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Construct secure installed-app payload without allowing protected field overrides."""
        if operation not in _ALLOWED_OPERATIONS:
            raise SecurityError(f"Samsung operation {operation!r} is not in safe allowlist")

        if override_params:
            for key in override_params:
                if key in _PROTECTED_FIELDS:
                    raise SecurityError(f"Protected field {key!r} cannot be overridden by caller")

        payload: dict[str, Any] = {
            "requester": "FIND_MY_MOBILE",
            "requesterToken": "b47285ea-2615-46eb-a1d2-28e4e94119d8",
            "method": "POST",
            "uri": f"/installedapps/devices/{device_id}/operations",
            "body": {
                "userUuid": user_uuid,
                "operation": operation,
            },
        }

        if override_params:
            payload["body"].update(override_params)

        return payload
