"""Application configuration."""

from __future__ import annotations

import os
import re
import sys
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError


@dataclass(frozen=True)
class Settings:
    config_dir: Path
    google_credentials_file: Path
    google_token_file: Path
    github_token: str | None
    github_project_id: str | None
    timezone: str
    working_day_start: str
    working_day_end: str
    calendar_id: str
    task_list_id: str
    attendees: tuple[str, ...]
    schedulable_statuses: frozenset[str]
    count_all_day_events: bool

    def require_github(self) -> tuple[str, str]:
        if not self.github_token or not self.github_project_id:
            raise ConfigurationError(
                "GitHub integration is not configured",
                hint="Set the GITHUB_TOKEN and GITHUB_PROJECT_ID environment variables.",
            )
        return self.github_token, self.github_project_id


def _config_dir(environ: Mapping[str, str]) -> Path:
    override = environ.get("CAL_AUTO_CONFIG_DIR")
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "win32":
        path = Path(environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "cal-auto-python"
    else:
        path = Path(environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cal-auto-python"
    path.mkdir(parents=True, exist_ok=True)
    if path.stat().st_uid == os.getuid():
        path.chmod(0o700)
    return path


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    config_dir = _config_dir(env)
    start = env.get("CAL_AUTO_WORKING_DAY_START", "09:00")
    end = env.get("CAL_AUTO_WORKING_DAY_END", "17:00")
    time_pattern = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    if not time_pattern.fullmatch(start) or not time_pattern.fullmatch(end):
        raise ConfigurationError(
            "Working hours must use strict HH:MM values",
            hint="Set CAL_AUTO_WORKING_DAY_START/CAL_AUTO_WORKING_DAY_END to HH:MM, e.g. 09:00.",
        )
    if start >= end:
        raise ConfigurationError(
            "Working day start must be earlier than end",
            hint="Adjust CAL_AUTO_WORKING_DAY_START/CAL_AUTO_WORKING_DAY_END so start precedes end.",
        )
    attendees = tuple(
        value.strip() for value in env.get("CAL_AUTO_ATTENDEES", "").split(",") if value.strip()
    )
    statuses = frozenset(
        value.strip()
        for value in env.get("CAL_AUTO_SCHEDULABLE_STATUSES", "Backlog").split(",")
        if value.strip()
    )
    timezone = env.get("CAL_AUTO_TIMEZONE", "").strip()
    if not timezone:
        raise ConfigurationError(
            "No timezone configured",
            hint="Set CAL_AUTO_TIMEZONE to an IANA timezone name, e.g. Europe/Lisbon.",
        )
    return Settings(
        config_dir=config_dir,
        google_credentials_file=config_dir / "credentials.json",
        google_token_file=config_dir / "token.json",
        github_token=env.get("GITHUB_TOKEN"),
        github_project_id=env.get("GITHUB_PROJECT_ID"),
        timezone=timezone,
        working_day_start=start,
        working_day_end=end,
        calendar_id=env.get("CAL_AUTO_CALENDAR_ID", "primary"),
        task_list_id=env.get("CAL_AUTO_TASK_LIST_ID", "@default"),
        attendees=attendees,
        schedulable_statuses=statuses,
        count_all_day_events=env.get("CAL_AUTO_COUNT_ALL_DAY_EVENTS", "false").lower() == "true",
    )


def legacy_auth_dir() -> Path:
    return Path.cwd() / "auth"


def warn_legacy_auth(path: Path) -> None:
    warnings.warn(
        f"Credentials found in legacy location {path}; move them to the configured directory.",
        UserWarning,
        stacklevel=2,
    )
