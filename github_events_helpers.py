"""GitHub Actions webhook events file I/O and workflow-run datetime helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

EVENTS_FILE = Path(__file__).parent / "github_events.json"
NOTIFICATION_STATE_FILE = Path(__file__).parent / "notification_state.json"


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


def _login_from_user_obj(obj: object) -> str | None:
    if not isinstance(obj, dict):
        return None
    login = obj.get("login")
    if isinstance(login, str) and login.strip():
        return login.strip()
    return None


def suggested_notify_github_login(event: dict, run: dict) -> tuple[str | None, str | None]:
    """Best-effort GitHub login to ping for a failed run (PR author, then trigger actor, etc.)."""
    prs = run.get("pull_requests")
    if isinstance(prs, list):
        for pr in prs:
            if not isinstance(pr, dict):
                continue
            lu = _login_from_user_obj(pr.get("user"))
            if lu:
                return lu, "pr_author"
    lu = _login_from_user_obj(run.get("triggering_actor"))
    if lu:
        return lu, "triggering_actor"
    lu = _login_from_user_obj(run.get("actor"))
    if lu:
        return lu, "actor"
    sender = event.get("sender")
    if isinstance(sender, str) and sender.strip():
        return sender.strip(), "sender"
    return None, None


def seen_runs_map() -> dict[str, str]:
    """Map workflow run id (str) -> ISO8601 seen_at. Empty if missing or invalid file."""
    if not NOTIFICATION_STATE_FILE.exists():
        return {}
    try:
        data = json.loads(NOTIFICATION_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = data.get("seen_run_ids")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        if isinstance(v, str) and v.strip():
            out[key] = v.strip()
        else:
            out[key] = iso_utc_z(datetime.now(timezone.utc))
    return out


def persist_seen_runs_map(seen: dict[str, str]) -> dict[str, str] | None:
    """Write full seen map. Returns error payload or None on success."""
    try:
        NOTIFICATION_STATE_FILE.write_text(
            json.dumps({"seen_run_ids": seen}, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        return {
            "error": "Failed to write notification state",
            "detail": str(exc),
            "notification_state_file": str(NOTIFICATION_STATE_FILE),
        }
    return None


def record_workflow_runs_seen(run_ids: list[str | int]) -> dict[str, object]:
    """Record workflow run ids as seen (idempotent). Returns result or error dict."""
    seen = seen_runs_map()
    now = iso_utc_z(datetime.now(timezone.utc))
    marked: list[str] = []
    for rid in run_ids:
        key = str(rid).strip()
        if not key:
            continue
        seen[key] = now
        marked.append(key)
    err = persist_seen_runs_map(seen)
    if err:
        return err
    return {
        "marked": marked,
        "marked_at": now,
        "notification_state_file": str(NOTIFICATION_STATE_FILE),
    }
