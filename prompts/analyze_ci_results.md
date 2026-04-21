Analyze recent CI activity.
1) Call `get_workflow_status()` for a snapshot of the latest run per workflow per repository. Use optional `workflow_name` / `conclusion` filters when narrowing down. Note per row: `conclusion`, `failure_unseen`, `suggested_notify_github_login`, `seen`.
2) Call `get_recent_actions_events(limit=20)` for raw webhook context if needed.
3) Summarize pass/fail trend, flaky or repeatedly failing jobs, unseen failures (`failure_unseen`), and top risks.
4) End with 3 prioritized next actions for the team. If failures were addressed or communicated, use `mark_workflow_runs_seen` with the `run_id` values from `get_workflow_status`.
