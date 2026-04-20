"""GitHub Actions webhook events file I/O and workflow-run datetime helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

EVENTS_FILE = Path(__file__).parent / "github_events.json"


def load_events_file() -> tuple[list[object] | None, dict[str, str] | None]:
    """Load and validate the events JSON array."""
    try:
        raw = EVENTS_FILE.read_text(encoding="utf-8")
        events = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return None, {
            "error": "Failed to read events file",
            "events_file": str(EVENTS_FILE),
            "detail": str(exc),
        }

    if not isinstance(events, list):
        return None, {
            "error": "Invalid events file format (expected a JSON array)",
            "events_file": str(EVENTS_FILE),
        }

    return events, None


def event_repository_key(event: dict) -> str:
    repo = event.get("repository")
    if isinstance(repo, str) and repo.strip():
        return repo.strip()
    return "unknown"


def parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def workflow_last_run_at(event: dict, run: dict) -> datetime | None:
    for key in ("updated_at", "created_at", "run_started_at"):
        dt = parse_iso_datetime(run.get(key))
        if dt is not None:
            return dt
    return parse_iso_datetime(event.get("timestamp"))


def format_time_since_last_run(last_run: datetime | None) -> str:
    if last_run is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    seconds = int((now - last_run).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        rem_m = minutes % 60
        if rem_m == 0:
            return f"{hours}h ago"
        return f"{hours}h {rem_m}m ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    return f"{weeks}w ago"


def iso_utc_z(dt: datetime) -> str:
    utc = dt.astimezone(timezone.utc).replace(microsecond=0)
    return utc.isoformat().replace("+00:00", "Z")
