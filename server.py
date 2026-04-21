#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from github_events_helpers import (
    EVENTS_FILE,
    NOTIFICATION_STATE_FILE,
    event_repository_key,
    format_time_since_last_run,
    iso_utc_z,
    load_events_file,
    record_workflow_runs_seen,
    seen_runs_map,
    suggested_notify_github_login,
    workflow_last_run_at,
)
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# PR template directory (local to this starter)
TEMPLATES_DIR = Path(__file__).parent / "templates"
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Normalizes caller labels to template stems (see starter/templates/*.md).
CHANGE_TYPE_ALIASES: dict[str, str] = {
    "fix": "bug",
    "bugfix": "bug",
    "feat": "feature",
    "refactor": "refact",
    "refactoring": "refact",
}


def _find_git_working_dir(workspace_root: str) -> tuple[str | None, str]:
    """If workspace_root is inside a git worktree, return (toplevel_path, ""). Else (None, reason)."""
    start = Path(workspace_root).resolve()
    for ancestor in [start, *start.parents]:
        a = str(ancestor)
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=a,
            capture_output=True,
            text=True,
            check=False,
        )
        if inside.returncode != 0:
            continue
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=a,
            capture_output=True,
            text=True,
            check=False,
        )
        if top.returncode != 0:
            continue
        toplevel = top.stdout.strip()
        return (toplevel if toplevel else a, a)
    return (None, f"no git repository at or above {workspace_root}")


def _load_prompt_text(filename: str) -> str:
    """Load a prompt body from prompts/*.md with a safe fallback."""
    path = PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            f"Prompt file '{filename}' is missing. "
            "Please create it in the prompts directory."
        )


@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main", include_diff: bool = True, diff_offset: int = 0
) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
        diff_offset: Starting line offset for paginated diff output (default: 0)
    """
    max_diff_lines = 500
    diff_offset = max(diff_offset, 0)

    workspace_root: str | None = None
    try:
        context = mcp.get_context()
        roots_result = await context.session.list_roots()
        if roots_result.roots:
            workspace_root = roots_result.roots[0].uri.path
    except Exception:
        pass

    if not workspace_root:
        workspace_root = os.getcwd()

    git_working_dir, _ = _find_git_working_dir(workspace_root)
    if not git_working_dir:
        return json.dumps(
            {
                "error": "Working directory is not a git repository",
                "mcp_workspace": workspace_root,
                "hint": "Use a workspace folder inside a git clone, or run git init in this folder.",
            }
        )

    def run_git(args: list[str]) -> tuple[bool, str]:
        result = subprocess.run(
            ["git", *args],
            cwd=git_working_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
            return False, err
        return True, result.stdout.rstrip()

    ok, _ = run_git(["rev-parse", "--is-inside-work-tree"])
    if not ok:
        return json.dumps(
            {
                "error": "Git repository could not be used",
                "mcp_workspace": workspace_root,
                "git_working_dir": git_working_dir,
            }
        )

    # Best effort update, non-fatal if remote is missing/offline.
    run_git(["fetch", "origin"])

    origin_ref = f"origin/{base_branch}"
    ok_origin_ref, _ = run_git(["rev-parse", "--verify", "--quiet", f"refs/remotes/{origin_ref}"])
    compare_ref = origin_ref if ok_origin_ref else base_branch

    ok_status, status = run_git(["status", "--short", "--branch"])
    ok_commits, commits = run_git(["log", "--oneline", "--decorate", "--graph", f"{compare_ref}..HEAD"])
    ok_files, changed_files_raw = run_git(["diff", "--name-only", f"{compare_ref}...HEAD"])
    ok_stat, diff_stat = run_git(["diff", "--stat", f"{compare_ref}...HEAD"])

    response: dict[str, object] = {
        "mcp_workspace": workspace_root,
        "working_dir": git_working_dir,
        "base_ref": compare_ref,
        "status": status if ok_status else "",
        "commits": commits if ok_commits else "",
        "changed_files": changed_files_raw.splitlines() if ok_files and changed_files_raw else [],
        "diff_stat": diff_stat if ok_stat else "",
    }

    if include_diff:
        ok_patch, patch = run_git(["diff", "--patch", "--function-context", "-U10", f"{compare_ref}...HEAD"])
        if ok_patch:
            diff_lines = patch.splitlines()
            total_lines = len(diff_lines)
            page_lines = diff_lines[diff_offset : diff_offset + max_diff_lines]
            returned_lines = len(page_lines)
            next_offset = diff_offset + returned_lines

            response["diff"] = "\n".join(page_lines)
            response["diff_offset"] = diff_offset
            response["diff_total_lines"] = len(diff_lines)
            response["diff_returned_lines"] = returned_lines
            response["diff_has_more"] = next_offset < total_lines
            response["diff_next_offset"] = next_offset if next_offset < total_lines else None
        else:
            response["diff_error"] = patch

    return json.dumps(response)


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    if not TEMPLATES_DIR.exists() or not TEMPLATES_DIR.is_dir():
        return json.dumps(
            {
                "error": "Templates directory not found",
                "templates_dir": str(TEMPLATES_DIR),
            }
        )

    template_files = sorted(TEMPLATES_DIR.glob("*.md"))
    if not template_files:
        return json.dumps(
            {
                "error": "No template files found",
                "templates_dir": str(TEMPLATES_DIR),
            }
        )

    items: list[dict[str, str]] = []
    skipped_files: dict[str, str] = {}

    for template_file in template_files:
        try:
            stem = template_file.stem
            content = template_file.read_text(encoding="utf-8")
            items.append(
                {
                    "id": stem,
                    "name": stem,
                    "type": stem,
                    "filename": template_file.name,
                    "content": content,
                }
            )
        except OSError as exc:
            skipped_files[template_file.name] = str(exc)

    if not items:
        return json.dumps(
            {
                "error": "No template files could be read",
                "templates_dir": str(TEMPLATES_DIR),
                **({"skipped_files": skipped_files} if skipped_files else {}),
            }
        )

    return json.dumps(items)


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Pick a PR template by change type (no server-side classification).

    Args:
        changes_summary: Optional context from the client; not used for mapping (kept for API compatibility).
        change_type: Template id: base, bug, feature, task, hotfix, refact.
            Aliases: fix/bugfix -> bug, feat -> feature, refactor/refactoring -> refact.
    """
    if not TEMPLATES_DIR.exists() or not TEMPLATES_DIR.is_dir():
        return json.dumps(
            {
                "error": "Templates directory not found",
                "templates_dir": str(TEMPLATES_DIR),
            }
        )

    stems = sorted(p.stem for p in TEMPLATES_DIR.glob("*.md"))
    if not stems:
        return json.dumps(
            {
                "error": "No template files found",
                "templates_dir": str(TEMPLATES_DIR),
            }
        )

    raw = change_type.strip().lower()
    key = CHANGE_TYPE_ALIASES.get(raw, raw)
    if key not in stems:
        key = "base" if "base" in stems else stems[0]

    path = TEMPLATES_DIR / f"{key}.md"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return json.dumps(
            {
                "error": "Failed to read template",
                "template": key,
                "detail": str(exc),
            }
        )

    payload: dict[str, object] = {
        "recommended_template": key,
        "template_content": content,
        "available_templates": stems,
        "change_type_normalized": key,
    }
    if changes_summary.strip():
        payload["changes_summary"] = changes_summary.strip()

    return json.dumps(payload)

# ===== Module 2: New GitHub Actions Tools =====
# Events path and file helpers: github_events_helpers (shared path with webhook_server.py)


@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    limit = max(1, min(int(limit), 100))

    if not EVENTS_FILE.exists():
        return json.dumps({"events": [], "count": 0, "events_file": str(EVENTS_FILE)})

    events, error = load_events_file()
    if error:
        return json.dumps(error)
    assert events is not None

    # File stores oldest-first; take the last `limit` and return newest-first
    tail = events[-limit:]
    recent = list(reversed(tail))

    return json.dumps(
        {
            "events": recent,
            "count": len(recent),
        }
    )


@mcp.tool()
async def get_workflow_status(
    workflow_name: Optional[str] = None,
    conclusion: Optional[str] = None,
) -> str:
    """Get the current status of GitHub Actions workflows, grouped by repository.

    Each workflow row includes run_id, seen / seen_at, failure_unseen (failure not yet marked seen),
    suggested_notify_github_login, and suggested_notify_source (pr_author, triggering_actor, actor, sender).

    Args:
        workflow_name: Optional workflow name substring (case-insensitive).
        conclusion: Optional filter on the latest run's conclusion, e.g. success or failure
            (case-insensitive; matches GitHub's workflow_run.conclusion).
    """
    if not EVENTS_FILE.exists():
        return json.dumps(
            {
                "repositories": [],
                "total_workflows": 0,
                "repositories_count": 0,
                "events_file": str(EVENTS_FILE),
                "notification_state_file": str(NOTIFICATION_STATE_FILE),
            }
        )

    events, error = load_events_file()
    if error:
        return json.dumps(error)
    assert events is not None

    seen_map = seen_runs_map()

    filtered_name = workflow_name.strip().lower() if workflow_name else None
    conclusion_filter = conclusion.strip().lower() if conclusion and conclusion.strip() else None

    workflow_events: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "workflow_run":
            continue

        run = event.get("workflow_run")
        if not isinstance(run, dict):
            continue

        name = run.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        if filtered_name and filtered_name not in name.lower():
            continue

        workflow_events.append(event)

    latest_by_repo_workflow: dict[tuple[str, str], dict[str, object]] = {}
    for event in workflow_events:
        run = event["workflow_run"]
        assert isinstance(run, dict)
        wf_name = run["name"]
        assert isinstance(wf_name, str)
        repo_key = event_repository_key(event)
        key = (repo_key, wf_name)

        current = latest_by_repo_workflow.get(key)
        if not current:
            latest_by_repo_workflow[key] = event
            continue

        event_ts = str(event.get("timestamp") or "")
        current_ts = str(current.get("timestamp") or "")
        if event_ts >= current_ts:
            latest_by_repo_workflow[key] = event

    by_repository: dict[str, list[dict[str, object]]] = {}
    for (_repo_key, _wf_name), event in latest_by_repo_workflow.items():
        run = event["workflow_run"]
        assert isinstance(run, dict)
        raw_conclusion = run.get("conclusion")
        conclusion_str = (
            str(raw_conclusion).strip().lower()
            if raw_conclusion is not None and str(raw_conclusion).strip()
            else ""
        )
        if conclusion_filter and conclusion_str != conclusion_filter:
            continue

        last_run = workflow_last_run_at(event, run)
        time_since = format_time_since_last_run(last_run)
        last_run_at = iso_utc_z(last_run) if last_run is not None else None

        repo_key = event_repository_key(event)
        run_id_raw = run.get("id")
        run_id = str(run_id_raw).strip() if run_id_raw is not None and str(run_id_raw).strip() else ""
        seen_at = seen_map.get(run_id) if run_id else None
        notify_login, notify_source = suggested_notify_github_login(event, run)
        item: dict[str, object] = {
            "name": run["name"],
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "branch": run.get("head_branch"),
            "event": run.get("event"),
            "run_number": run.get("run_number"),
            "run_attempt": run.get("run_attempt"),
            "updated_at": run.get("updated_at"),
            "html_url": run.get("html_url"),
            "repository": event.get("repository"),
            "received_at": event.get("timestamp"),
            "time_since_last_run": time_since,
            "last_run_at": last_run_at,
            "run_id": run_id if run_id else None,
            "seen": bool(run_id and run_id in seen_map),
            "seen_at": seen_at,
            "failure_unseen": bool(
                run_id
                and conclusion_str == "failure"
                and run_id not in seen_map
            ),
            "suggested_notify_github_login": notify_login,
            "suggested_notify_source": notify_source,
        }
        if last_run is not None:
            item["seconds_since_last_run"] = int(
                (datetime.now(timezone.utc) - last_run).total_seconds()
            )
        by_repository.setdefault(repo_key, []).append(item)

    for wf_list in by_repository.values():
        wf_list.sort(
            key=lambda row: (
                float(row.get("seconds_since_last_run", 1e18))
                if isinstance(row.get("seconds_since_last_run"), int)
                else 1e18
            ),
        )

    repository_entries = []
    for repo in sorted(by_repository.keys()):
        wf_list = by_repository[repo]
        repository_entries.append(
            {
                "repository": repo,
                "workflows": wf_list,
                "count": len(wf_list),
            }
        )

    total = sum(len(e["workflows"]) for e in repository_entries)

    payload: dict[str, object] = {
        "repositories": repository_entries,
        "total_workflows": total,
        "repositories_count": len(repository_entries),
        "notification_state_file": str(NOTIFICATION_STATE_FILE),
    }
    if workflow_name:
        payload["workflow_name_filter"] = workflow_name
    if conclusion:
        payload["conclusion_filter"] = conclusion

    return json.dumps(payload)


@mcp.tool()
async def mark_workflow_runs_seen(run_ids: list[int | str]) -> str:
    """Mark GitHub Actions workflow runs as seen (acknowledged / already notified).

    Args:
        run_ids: One or more workflow run ids (same as workflow_run.id from GitHub).
    """
    if not run_ids:
        return json.dumps(
            {
                "error": "run_ids is required",
                "hint": "Pass run_id values from get_workflow_status rows.",
            }
        )
    result = record_workflow_runs_seen(run_ids)
    return json.dumps(result)


# ===== Module 2: MCP Prompts =====

@mcp.prompt()
async def analyze_ci_results():
    """Analyze recent CI/CD results and provide insights."""
    return _load_prompt_text("analyze_ci_results.md")


@mcp.prompt()
async def create_deployment_summary():
    """Generate a deployment summary for team communication."""
    return _load_prompt_text("create_deployment_summary.md")


@mcp.prompt()
async def generate_pr_status_report():
    """Generate a comprehensive PR status report including CI/CD results."""
    return _load_prompt_text("generate_pr_status_report.md")


@mcp.prompt()
async def pr_review_with_ci_checklist():
    """PR review: combine code diff + CI/CD status + reviewer checklist."""
    return _load_prompt_text("pr_review_with_ci_checklist.md")


@mcp.prompt()
async def troubleshoot_workflow_failure():
    """Help troubleshoot a failing GitHub Actions workflow."""
    return _load_prompt_text("troubleshoot_workflow_failure.md")


if __name__ == "__main__":
    print("Starting PR Agent MCP server...")
    print("NOTE: Run webhook_server.py in a separate terminal to receive GitHub events")
    mcp.run()

