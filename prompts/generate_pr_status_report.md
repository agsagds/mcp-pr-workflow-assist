Generate a PR status report that combines code review and CI/CD health.
1) Call get_recent_actions_events(limit=20).
2) Use get_workflow_status() for workflows tied to the PR branch or related checks.
3) Produce sections: Overall Status, CI Checks, Failures/Warnings, Merge Readiness.
4) Include clear recommendation: ready to merge / needs fixes, with reasons.
