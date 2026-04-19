#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

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

# Persisted by webhook_server.py (same path)
EVENTS_FILE = Path(__file__).parent / "github_events.json"


def _load_events_file() -> tuple[list[object] | None, dict[str, str] | None]:
    """Load and validate the events file content."""
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


@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    limit = max(1, min(int(limit), 100))

    if not EVENTS_FILE.exists():
        return json.dumps({"events": [], "count": 0, "events_file": str(EVENTS_FILE)})

    events, error = _load_events_file()
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
async def get_workflow_status(workflow_name: Optional[str] = None) -> str:
    """Get the current status of GitHub Actions workflows.
    
    Args:
        workflow_name: Optional specific workflow name to filter by
    """
    if not EVENTS_FILE.exists():
        return json.dumps(
            {
                "workflows": [],
                "count": 0,
                "events_file": str(EVENTS_FILE),
            }
        )

    events, error = _load_events_file()
    if error:
        return json.dumps(error)
    assert events is not None

    filtered_name = workflow_name.strip().lower() if workflow_name else None

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

    latest_by_workflow: dict[str, dict[str, object]] = {}
    for event in workflow_events:
        run = event["workflow_run"]
        assert isinstance(run, dict)
        name = run["name"]
        assert isinstance(name, str)

        current = latest_by_workflow.get(name)
        if not current:
            latest_by_workflow[name] = event
            continue

        event_ts = str(event.get("timestamp") or "")
        current_ts = str(current.get("timestamp") or "")
        if event_ts >= current_ts:
            latest_by_workflow[name] = event

    workflows = []
    for name, event in latest_by_workflow.items():
        run = event["workflow_run"]
        assert isinstance(run, dict)
        workflows.append(
            {
                "name": name,
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
            }
        )

    workflows.sort(
        key=lambda item: str(item.get("received_at") or item.get("updated_at") or ""),
        reverse=True,
    )

    return json.dumps(
        {
            "workflows": workflows,
            "count": len(workflows),
            **({"workflow_name_filter": workflow_name} if workflow_name else {}),
        }
    )


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

