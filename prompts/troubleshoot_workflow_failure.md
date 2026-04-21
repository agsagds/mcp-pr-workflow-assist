Troubleshoot a failing GitHub Actions workflow.
1) Call `get_workflow_status(conclusion="failure")` (or without filter) and read each workflow row: `failure_unseen`, `seen`, `run_id`, `suggested_notify_github_login`, `suggested_notify_source`, `html_url`, `branch`, `repository`.
2) Prioritize rows where `failure_unseen` is true — these are failures not yet marked seen in `notification_state_file`.
3) For deeper context, call `get_recent_actions_events(limit=25)` and isolate failed `workflow_run` events.
4) When the user has triaged or notified someone, call `mark_workflow_runs_seen` with the relevant `run_id` values from step 1.
5) Identify failure pattern (new regression, intermittent, or infra-related).
6) Provide likely root cause, immediate fix steps, and prevention actions. Mention who to ping using `suggested_notify_github_login` when present (it is a hint, not guaranteed ownership).
