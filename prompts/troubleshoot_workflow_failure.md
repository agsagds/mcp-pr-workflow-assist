Troubleshoot a failing GitHub Actions workflow.
1) Call get_recent_actions_events(limit=25) and isolate failed workflow_run events.
2) For each failed workflow, call get_workflow_status(workflow_name=...).
3) Identify failure pattern (new regression, intermittent, or infra-related).
4) Provide likely root cause, immediate fix steps, and prevention actions.
