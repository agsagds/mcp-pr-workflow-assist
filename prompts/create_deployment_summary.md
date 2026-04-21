Create a concise deployment summary for the team.
Use `get_workflow_status()` (and optionally `get_recent_actions_events(limit=15)`). Call out any `failure_unseen` rows, who to ping (`suggested_notify_github_login`), and links (`html_url`).
Report: deployment status, latest successful run, current blockers, impacted branch/repo, and links.
Finish with a short Slack-ready message. After sending, you may mark runs seen with `mark_workflow_runs_seen` using `run_id` from `get_workflow_status`.
