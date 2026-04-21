"""Tests for notification state and get_workflow_status enrichment."""

import json
from pathlib import Path

import pytest

import github_events_helpers as ge
import server
from server import get_workflow_status, mark_workflow_runs_seen


def test_suggested_notify_pr_author() -> None:
    event: dict = {"sender": "backup"}
    run: dict = {
        "pull_requests": [{"user": {"login": "author1"}}],
        "triggering_actor": {"login": "trigger"},
    }
    login, src = ge.suggested_notify_github_login(event, run)
    assert login == "author1"
    assert src == "pr_author"


def test_suggested_notify_triggering_actor() -> None:
    event: dict = {"sender": "senderx"}
    run: dict = {
        "pull_requests": [],
        "triggering_actor": {"login": "trigger"},
        "actor": {"login": "actorx"},
    }
    login, src = ge.suggested_notify_github_login(event, run)
    assert login == "trigger"
    assert src == "triggering_actor"


def test_suggested_notify_sender_fallback() -> None:
    event: dict = {"sender": "  onlysender  "}
    run: dict = {"pull_requests": []}
    login, src = ge.suggested_notify_github_login(event, run)
    assert login == "onlysender"
    assert src == "sender"


@pytest.mark.asyncio
async def test_get_workflow_status_seen_and_notify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events_f = tmp_path / "ev.json"
    state_f = tmp_path / "notification_state.json"
    monkeypatch.setattr(ge, "EVENTS_FILE", events_f)
    monkeypatch.setattr(server, "EVENTS_FILE", events_f)
    monkeypatch.setattr(ge, "NOTIFICATION_STATE_FILE", state_f)
    monkeypatch.setattr(server, "NOTIFICATION_STATE_FILE", state_f)

    events_f.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-04-20T00:00:00",
                    "event_type": "workflow_run",
                    "repository": "org/repo",
                    "sender": "pusher",
                    "workflow_run": {
                        "id": 999001,
                        "name": "CI",
                        "status": "completed",
                        "conclusion": "failure",
                        "head_branch": "main",
                        "pull_requests": [{"user": {"login": "prwriter"}}],
                        "triggering_actor": {"login": "ignored_when_pr"},
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    raw = await get_workflow_status()
    data = json.loads(raw)
    wf = data["repositories"][0]["workflows"][0]
    assert wf["run_id"] == "999001"
    assert wf["seen"] is False
    assert wf["failure_unseen"] is True
    assert wf["suggested_notify_github_login"] == "prwriter"
    assert wf["suggested_notify_source"] == "pr_author"

    mark_raw = await mark_workflow_runs_seen([999001])
    mark_data = json.loads(mark_raw)
    assert "marked" in mark_data
    assert "999001" in mark_data["marked"]

    raw2 = await get_workflow_status()
    data2 = json.loads(raw2)
    wf2 = data2["repositories"][0]["workflows"][0]
    assert wf2["seen"] is True
    assert wf2["failure_unseen"] is False
    assert wf2["seen_at"]
