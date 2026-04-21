Generate a PR status report that combines code review and CI/CD health.
1) Call `get_workflow_status()` (optionally `conclusion="failure"` to focus on red checks). Include in the report: `branch`, `conclusion`, `failure_unseen`, `suggested_notify_github_login`, `run_id`, `html_url`.
2) Optionally call `get_recent_actions_events(limit=20)` for extra webhook detail.
3) Produce sections: Overall Status, CI Checks, Failures/Warnings, Merge Readiness.
4) Include clear recommendation: ready to merge / needs fixes, with reasons. After the user confirms failures are handled, suggest `mark_workflow_runs_seen` with the relevant `run_id` values.
