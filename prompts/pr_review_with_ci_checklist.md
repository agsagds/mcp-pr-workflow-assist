You are helping a human reviewer complete a PR review. Combine **code evidence** with **CI/CD evidence**, then deliver a **reviewer checklist** the human can work through.

## Gather inputs (use MCP tools)

**Code changes**

1. Call `analyze_file_changes` with `base_branch` appropriate for this repo (default `main` if unsure). Use `include_diff=true`. If the diff is paginated (`diff_has_more`), call again with `diff_next_offset` until you have enough context for a solid review (or state clearly what is still unseen).
2. Optionally call `get_pr_templates` and/or `suggest_template` if the PR type is known (bug/feature/refact/etc.) so the review aligns with the expected PR shape.

**CI/CD**

3. Call `get_recent_actions_events(limit=20)` for recent GitHub Actions webhook activity.
4. Call `get_workflow_status()` for the latest run per workflow **per repository**. The JSON is grouped under `repositories` (each entry has `repository`, `workflows`, `count`). Each workflow row includes `status`, `conclusion`, `html_url`, `time_since_last_run`, `last_run_at`, and `branch` when known. Optional arguments:
   - `workflow_name`: substring match on the workflow display name (case-insensitive).
   - `conclusion`: filter to runs whose latest `conclusion` matches exactly (case-insensitive), e.g. `success` or `failure` (useful to list only red or only green workflows). Omit both for the full snapshot.

If any tool returns an error or empty data, say so explicitly and proceed with what you have—do not invent CI or git facts.

## Produce the review (structure)

Write for a reviewer skimming quickly. Use the sections below in order.

### 1. Summary

- One short paragraph: what this PR does and overall risk (low/medium/high) with one-line justification.

### 2. Code review — findings

- Bullets grouped by **severity**: **Blocker** / **Should fix** / **Nit**.
- Each bullet ties to **concrete evidence** (file path, behavior, or diff hunk you saw). If something is uncertain, label it as a **question** instead of asserting.

### 3. CI/CD status

- Table or bullets: **repository**, workflow name, branch (if known), `status` / `conclusion`, `time_since_last_run` or `last_run_at`, link (`html_url`) when present.
- Call out **failing**, **cancelled**, or **missing** checks relative to merge expectations.
- Note staleness: use `time_since_last_run` from `get_workflow_status`, or say if events look old or unrelated to this PR.

### 4. Reviewer checklist (interactive)

Output a **markdown checklist** the reviewer can tick in their editor. Each item must be **binary** (pass/fail or done/not done). Include at least:

- [ ] **Correctness**: Logic matches intent; edge cases handled; no obvious regressions in touched paths.
- [ ] **Tests**: Adequate coverage or manual test plan for the change; CI test jobs green or failures explained.
- [ ] **Security & data**: No secrets; validation/authz considered where inputs cross trust boundaries.
- [ ] **Observability**: Logging/metrics/errors appropriate for new failure modes.
- [ ] **Compatibility**: API/DB/schema migrations backward compatible or safely flagged.
- [ ] **Performance**: Hot paths acceptable; no accidental N+1 or unbounded work.
- [ ] **CI/CD gates**: Required workflows successful for this branch; no unexplained red checks.
- [ ] **Docs & rollout**: README/changelog/runbooks updated if behavior or ops change.

Add **2–4 extra checklist items** tailored to this specific PR (derived from the diff and CI), not generic filler.

### 5. Merge recommendation

- State **Approve / Request changes / Comment only** with reasons grounded in sections 2–4.
- If CI is red or unknown, default to **Request changes** or **Comment only** unless the human explicitly overrides—say why.

Keep the tone factual and concise. Prefer checklist items and bullets over long prose.
