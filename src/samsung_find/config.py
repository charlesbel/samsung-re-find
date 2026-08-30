"""Configuration for Samsung Find client and SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
    DEFAULT_PENDING_PATH,
    DEFAULT_REDIRECT_PATH,
    DEFAULT_STATE_PATH,
    DEFAULT_TIMEZONE,
)
from .credentials import resolve_master_state_path


@dataclass(frozen=True)
class FindConfig:
    """Immutable configuration for SamsungFind client and services."""

    country: str = DEFAULT_COUNTRY
    language: str = DEFAULT_LANGUAGE
    timezone: str = DEFAULT_TIMEZONE
    timeout_s: float = 30.0
    master_state_path: Path | None = None
    state_path: Path | None = None
    pending_path: Path | None = None
    redirect_path: Path | None = None

    def __post_init__(self) -> None:
        # Load env vars if defaults
        country = os.environ.get("SAMSUNG_FIND_COUNTRY", self.country).upper()
        language = os.environ.get("SAMSUNG_FIND_LANGUAGE", self.language)
        timezone = os.environ.get("SAMSUNG_FIND_TIMEZONE", self.timezone)

        master_path = self.master_state_path or resolve_master_state_path()
        state_p = (
            Path(self.state_path).expanduser().resolve()
            if self.state_path
            else Path(DEFAULT_STATE_PATH).expanduser().resolve()
        )
        pending_p = (
            Path(self.pending_path).expanduser().resolve()
            if self.pending_path
            else Path(DEFAULT_PENDING_PATH).expanduser().resolve()
        )
        redirect_p = (
            Path(self.redirect_path).expanduser().resolve()
            if self.redirect_path
            else Path(DEFAULT_REDIRECT_PATH).expanduser().resolve()
        )

        object.__setattr__(self, "country", country)
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "timezone", timezone)
        object.__setattr__(self, "master_state_path", master_path)
        object.__setattr__(self, "state_path", state_p)
        object.__setattr__(self, "pending_path", pending_p)
        object.__setattr__(self, "redirect_path", redirect_p)
