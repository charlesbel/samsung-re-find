"""Secure transport layer for SmartThings and Samsung APIs."""

from __future__ import annotations

import posixpath
import re
import urllib.parse
from collections.abc import Callable
from typing import Any

import httpx

from .constants import (
    FIND_REQUESTER_NAME,
    FIND_REQUESTER_TOKEN,
    SMARTTHINGS_USER_AGENT,
)
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

_ALLOWED_PAGINATION_PATH_PREFIXES = (
    "/installedapps",
    "/devices",
    "/locations",
    "/users",
)


def validate_pagination_path(raw_path: str) -> str:
    """Percent-decode and canonicalize path safely.

    Rejects encoded traversal, separators, backslashes, and double encoding.
    """
    if not isinstance(raw_path, str) or not raw_path.startswith("/"):
        raise SecurityError("Pagination URL path must start with '/'")

    # Reject backslash characters (raw and encoded)
    if "\\" in raw_path or "%5c" in raw_path.lower():
        raise SecurityError("Backslash in pagination URL path is forbidden")

    # Reject null bytes (raw and encoded)
    if "\x00" in raw_path or "%00" in raw_path.lower():
        raise SecurityError("Null byte in pagination URL path is forbidden")

    # Reject encoded path separators (%2f / %2F)
    if "%2f" in raw_path.lower():
        raise SecurityError("Encoded path separator in pagination URL path is forbidden")

    # Reject double / nested percent encoding (e.g. %25...)
    if "%25" in raw_path.lower():
        raise SecurityError("Double percent-encoding detected in pagination URL path")

    # Reject encoded dots/traversal (%2e / %2E)
    if "%2e" in raw_path.lower():
        raise SecurityError("Encoded path traversal sequence detected in pagination URL path")

    # Reject malformed percent escapes before decoding.
    if re.search(r"%(?![0-9A-Fa-f]{2})", raw_path):
        raise SecurityError("Malformed percent-encoding in pagination URL path")

    # Percent-decode bytes, then require canonical UTF-8. urllib.parse.unquote()
    # would replace malformed sequences with U+FFFD and could make hostile paths
    # appear innocuous to the segment allowlist.
    try:
        decoded_path = urllib.parse.unquote_to_bytes(raw_path).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SecurityError("Invalid UTF-8 in pagination URL path") from exc

    # Reject if another level of decoding is possible or if decoded characters contain forbidden chars
    if urllib.parse.unquote(decoded_path) != decoded_path:
        raise SecurityError("Double percent-encoding detected in pagination URL path")

    if "\\" in decoded_path or "\x00" in decoded_path:
        raise SecurityError("Unsafe character detected after URL path decoding")

    # Canonicalize path
    canonical_path = posixpath.normpath(decoded_path)

    if not canonical_path.startswith("/"):
        canonical_path = "/" + canonical_path

    # Check segment allowlist against canonical path
    if not any(
        canonical_path == prefix or canonical_path.startswith(f"{prefix}/")
        for prefix in _ALLOWED_PAGINATION_PATH_PREFIXES
    ):
        raise SecurityError(f"Unauthorized pagination endpoint path: {raw_path}")

    return canonical_path


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
    """Hardened HTTP transport enforcing destination allowlists, no-retry POSTs, and safe redirects."""

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
        self.http = http_client or httpx.Client(timeout=timeout, follow_redirects=False)

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

    def _send_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        **kwargs: Any,
    ) -> httpx.Response:
        intended_url = validate_smartthings_url(url)
        method_upper = method.upper()
        try:
            request = self.http.build_request(method_upper, intended_url, headers=headers, **kwargs)
            # Per-request override is required because callers may inject a Client
            # configured with follow_redirects=True.
            response = self.http.send(request, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise NetworkError(f"SmartThings request failed: {exc}") from exc

        if response.history:
            raise SecurityError("Redirect history on authenticated request is forbidden")
        if 300 <= response.status_code < 400:
            raise SecurityError(
                f"Redirect (HTTP {response.status_code}) on authenticated {method_upper} request is forbidden"
            )

        try:
            final_url = response.url
        except RuntimeError as exc:
            raise SecurityError("Authenticated response omitted its final destination") from exc
        if self._destination_identity(final_url) != self._destination_identity(request.url):
            raise SecurityError("Authenticated response final destination differs from intended request")
        return response

    @staticmethod
    def _destination_identity(url: httpx.URL) -> tuple[str, str, int | None, bytes, bytes]:
        """Return exact security-relevant URL components, including effective port."""
        effective_port = url.port
        if effective_port is None:
            effective_port = 443 if url.scheme == "https" else 80 if url.scheme == "http" else None
        raw_path = url.raw_path.split(b"?", 1)[0]
        return (url.scheme, url.host, effective_port, raw_path, url.query)

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        retry_auth: bool = True,
    ) -> httpx.Response:
        """Send an authenticated GET request with automatic retry on 401 (idempotent read)."""
        headers = self._headers()
        response = self._send_request("GET", url, headers=headers, params=params)

        if response.status_code in (401, 403) and retry_auth:
            headers = self._headers(force_refresh=True)
            response = self._send_request("GET", url, headers=headers, params=params)

        return response

    def _execute_operation(
        self,
        *,
        installed_app_id: str,
        operation: str,
        device_id: str,
        user_uuid: str,
        operation_params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute one internally selected operation without retrying the secret POST."""
        for identifier in (installed_app_id, device_id, user_uuid):
            if not isinstance(identifier, str) or not identifier or any(ch in identifier for ch in "/?#\\"):
                raise SecurityError("Invalid SmartThings operation identifier")
        payload = self.build_installed_app_payload(
            operation=operation,
            device_id=device_id,
            user_uuid=user_uuid,
            override_params=operation_params,
        )
        url = f"https://api.smartthings.com/installedapps/{installed_app_id}/execute"
        response = self._send_request("POST", url, headers=self._headers(), json=payload)
        if response.status_code in (401, 403):
            raise AuthError(
                f"Authentication failure during action execution (HTTP {response.status_code}); "
                "automatic retry disabled for non-idempotent action"
            )
        return response

    def check_connection(self, *, installed_app_id: str, device_id: str, user_uuid: str) -> httpx.Response:
        return self._execute_operation(
            installed_app_id=installed_app_id,
            operation="CHECK_CONNECTION",
            device_id=device_id,
            user_uuid=user_uuid,
        )

    def request_location(self, *, installed_app_id: str, device_id: str, user_uuid: str) -> httpx.Response:
        return self._execute_operation(
            installed_app_id=installed_app_id,
            operation="LOCATION",
            device_id=device_id,
            user_uuid=user_uuid,
        )

    def ring(
        self,
        *,
        installed_app_id: str,
        device_id: str,
        user_uuid: str,
        status: str,
    ) -> httpx.Response:
        if status not in {"start", "stop"}:
            raise SecurityError("Ring status must be 'start' or 'stop'")
        return self._execute_operation(
            installed_app_id=installed_app_id,
            operation="RING",
            device_id=device_id,
            user_uuid=user_uuid,
            operation_params={"status": status},
        )

    def set_tracking(
        self,
        *,
        installed_app_id: str,
        device_id: str,
        user_uuid: str,
        enabled: bool,
    ) -> httpx.Response:
        if type(enabled) is not bool:
            raise SecurityError("Tracking enabled must be a boolean")
        return self._execute_operation(
            installed_app_id=installed_app_id,
            operation="TRACK_LOCATION_START" if enabled else "TRACK_LOCATION_STOP",
            device_id=device_id,
            user_uuid=user_uuid,
        )

    def paginate(
        self,
        initial_url: str,
        params: dict[str, Any] | None = None,
        *,
        max_pages: int = 50,
    ) -> list[dict[str, Any]]:
        """Paginate a collection with strict same-host, path-allowlist, max pages, and loop detection."""
        items: list[dict[str, Any]] = []
        current_url: str | None = initial_url
        current_params = params
        seen_pages = {initial_url}
        page_count = 0

        while current_url:
            page_count += 1
            if page_count > max_pages:
                raise NetworkError(f"Pagination exceeded maximum allowed pages ({max_pages})")

            valid_url = validate_smartthings_url(current_url, base_url=initial_url)
            parsed_path = urllib.parse.urlparse(valid_url).path
            validate_pagination_path(parsed_path)

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
                    resolved_next = urllib.parse.urljoin(valid_url, str(next_href))
                    if resolved_next in seen_pages:
                        raise SecurityError("Pagination loop detected")
                    seen_pages.add(resolved_next)
                    current_url = resolved_next
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
            "requester": FIND_REQUESTER_NAME,
            "requesterToken": FIND_REQUESTER_TOKEN,
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
