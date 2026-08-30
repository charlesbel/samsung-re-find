"""Configuration for Samsung Find client and SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
    DEFAULT_TIMEZONE,
)
from .credentials import (
    resolve_find_state_path,
    resolve_legacy_find_state_path,
    resolve_master_state_path,
    resolve_pending_path,
    resolve_redirect_path,
)


@dataclass(frozen=True)
class FindConfig:
    """Immutable configuration for SamsungFind client and services."""

    country: str = DEFAULT_COUNTRY
    language: str = DEFAULT_LANGUAGE
    timezone: str = DEFAULT_TIMEZONE
    timeout_s: float = 30.0
    master_state_path: Path | None = None
    state_path: Path | None = None
    legacy_state_path: Path | None = None
    pending_path: Path | None = None
    redirect_path: Path | None = None

    def __post_init__(self) -> None:
        country = os.environ.get("SAMSUNG_FIND_COUNTRY", self.country).upper()
        language = os.environ.get("SAMSUNG_FIND_LANGUAGE", self.language)
        timezone = os.environ.get("SAMSUNG_FIND_TIMEZONE", self.timezone)

        master_path = self.master_state_path or resolve_master_state_path()
        state_p = self.state_path or resolve_find_state_path()
        legacy_p = self.legacy_state_path or resolve_legacy_find_state_path()
        pending_p = self.pending_path or resolve_pending_path()
        redirect_p = self.redirect_path or resolve_redirect_path()

        object.__setattr__(self, "country", country)
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "timezone", timezone)
        object.__setattr__(self, "master_state_path", Path(master_path).expanduser().resolve())
        object.__setattr__(self, "state_path", Path(state_p).expanduser().resolve())
        object.__setattr__(self, "legacy_state_path", Path(legacy_p).expanduser().resolve())
        object.__setattr__(self, "pending_path", Path(pending_p).expanduser().resolve())
        object.__setattr__(self, "redirect_path", Path(redirect_p).expanduser().resolve())
