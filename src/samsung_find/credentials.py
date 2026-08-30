"""Shared Samsung Account Master Credentials Contract (v1)."""

from __future__ import annotations

import os
import sys
import time
import urllib.parse
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import AuthError, SecurityError, StorageError
from .storage import atomic_write_json, locked, read_json

MASTER_SCHEMA_ID = "io.github.charlesbel.samsung-account.master"
MASTER_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MasterAccount:
    login_id: str
    user_id: str | None = None

    def __repr__(self) -> str:
        return f"MasterAccount(login_id='[REDACTED]', user_id={('[REDACTED]' if self.user_id else None)!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class MasterInstallation:
    physical_address: str

    def __repr__(self) -> str:
        return "MasterInstallation(physical_address='[REDACTED]')"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class MasterIdentity:
    auth_server_url: str
    userauth_token: str

    def __repr__(self) -> str:
        return f"MasterIdentity(auth_server_url={self.auth_server_url!r}, userauth_token='***')"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class MasterState:
    schema: str
    schema_version: int
    generation: str
    created_at: float
    updated_at: float
    account: MasterAccount
    installation: MasterInstallation
    identity: MasterIdentity

    def __repr__(self) -> str:
        return (
            f"MasterState(schema={self.schema!r}, schema_version={self.schema_version!r}, "
            f"generation={self.generation!r}, account={self.account!r}, "
            f"installation={self.installation!r}, identity={self.identity!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "generation": self.generation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "account": {
                "login_id": self.account.login_id,
                "user_id": self.account.user_id,
            },
            "installation": {
                "physical_address": self.installation.physical_address,
            },
            "identity": {
                "auth_server_url": self.identity.auth_server_url,
                "userauth_token": self.identity.userauth_token,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MasterState:
        if not isinstance(data, dict):
            raise StorageError("Master state is not a valid JSON object")

        schema = data.get("schema")
        if schema != MASTER_SCHEMA_ID:
            raise AuthError(f"Unsupported master schema: {schema!r}")

        version = data.get("schema_version")
        if version != MASTER_SCHEMA_VERSION:
            raise AuthError(f"Unsupported master schema version: {version!r}")

        generation = str(data.get("generation", ""))
        if not generation:
            raise AuthError("Master state missing generation identifier")

        created_at = float(data.get("created_at", time.time()))
        updated_at = float(data.get("updated_at", time.time()))

        account_raw = data.get("account") or {}
        if not isinstance(account_raw, dict) or not account_raw.get("login_id"):
            raise AuthError("Master state missing account.login_id")
        account = MasterAccount(
            login_id=str(account_raw["login_id"]),
            user_id=str(account_raw["user_id"]) if account_raw.get("user_id") else None,
        )

        installation_raw = data.get("installation") or {}
        if not isinstance(installation_raw, dict) or not installation_raw.get("physical_address"):
            raise AuthError("Master state missing installation.physical_address")
        installation = MasterInstallation(
            physical_address=str(installation_raw["physical_address"]),
        )

        identity_raw = data.get("identity") or {}
        if not isinstance(identity_raw, dict) or not identity_raw.get("userauth_token"):
            raise AuthError("Master state missing identity.userauth_token")

        auth_server = validate_auth_server_url(str(identity_raw.get("auth_server_url", "")))

        identity = MasterIdentity(
            auth_server_url=auth_server,
            userauth_token=str(identity_raw["userauth_token"]),
        )

        return cls(
            schema=schema,
            schema_version=version,
            generation=generation,
            created_at=created_at,
            updated_at=updated_at,
            account=account,
            installation=installation,
            identity=identity,
        )


def validate_auth_server_url(value: str) -> str:
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
        raise SecurityError("Invalid authentication server URL port") from exc

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
        raise SecurityError(f"Untrusted authentication server host: {hostname or 'unknown'}")
    return f"https://{hostname}"


def resolve_master_state_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve the master state file location using standard priority order."""
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    env_path = os.environ.get("SAMSUNG_ACCOUNT_MASTER_STATE")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return (base / "samsung-account" / "master.json").resolve()
    elif sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "samsung-account" / "master.json").resolve()
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return (base / "samsung-account" / "master.json").resolve()


def resolve_legacy_find_state_path() -> Path:
    """Resolve the legacy Find state file path."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config) if xdg_config else Path.home() / ".config"
    return (base / "samsung-find" / "state.json").resolve()


class MasterStateStore:
    """Store for managing shared Samsung master credentials."""

    def __init__(
        self,
        master_path: str | Path | None = None,
        legacy_path: str | Path | None = None,
    ):
        self.master_path = resolve_master_state_path(master_path)
        self.legacy_path = Path(legacy_path).expanduser().resolve() if legacy_path else resolve_legacy_find_state_path()

    def exists(self) -> bool:
        return self.master_path.exists()

    def load(self, *, allow_legacy_fallback: bool = True) -> MasterState | None:
        if self.master_path.exists():
            with locked(self.master_path):
                data = read_json(self.master_path)
                return MasterState.from_dict(data)

        if allow_legacy_fallback and self.legacy_path.exists():
            warnings.warn(
                "Using legacy authentication state from samsung-find. "
                "Run 'samsung-find auth migrate-master' to migrate.",
                UserWarning,
                stacklevel=2,
            )
            with locked(self.legacy_path):
                data = read_json(self.legacy_path)
                userauth = data.get("userauth_token")
                if not userauth:
                    return None
                auth_server = validate_auth_server_url(data.get("auth_server_url", "https://auth.samsungosp.com"))
                return MasterState(
                    schema=MASTER_SCHEMA_ID,
                    schema_version=MASTER_SCHEMA_VERSION,
                    generation=str(uuid.uuid4()),
                    created_at=float(data.get("created_at", time.time())),
                    updated_at=float(data.get("created_at", time.time())),
                    account=MasterAccount(
                        login_id=str(data.get("login_id", "legacy_user")),
                        user_id=str(data.get("user_id")) if data.get("user_id") else None,
                    ),
                    installation=MasterInstallation(
                        physical_address=str(data.get("device_id", "legacy_device")),
                    ),
                    identity=MasterIdentity(
                        auth_server_url=auth_server,
                        userauth_token=str(userauth),
                    ),
                )

        return None

    def save(
        self,
        login_id: str,
        physical_address: str,
        auth_server_url: str,
        userauth_token: str,
        user_id: str | None = None,
        generation: str | None = None,
    ) -> MasterState:
        auth_server = validate_auth_server_url(auth_server_url)
        gen = generation or str(uuid.uuid4())
        now = time.time()

        # If master state already existed, keep created_at
        created_at = now
        if self.master_path.exists():
            try:
                existing = self.load(allow_legacy_fallback=False)
                if existing:
                    created_at = existing.created_at
            except Exception:
                pass

        state = MasterState(
            schema=MASTER_SCHEMA_ID,
            schema_version=MASTER_SCHEMA_VERSION,
            generation=gen,
            created_at=created_at,
            updated_at=now,
            account=MasterAccount(login_id=login_id, user_id=user_id),
            installation=MasterInstallation(physical_address=physical_address),
            identity=MasterIdentity(
                auth_server_url=auth_server,
                userauth_token=userauth_token,
            ),
        )

        with locked(self.master_path):
            atomic_write_json(self.master_path, state.to_dict())

        return state
