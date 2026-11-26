"""The rules of a run: routes, limits, retries, the sandbox, the risk score, prompt budgets and skill checks.

A rule is a plain function with explicit arguments: it returns a value or a decision, or raises ``Stop``; it never takes
the conductor (``self``), writes a file, prints progress or sends an event. What reads or records the run around a rule lives in
``application`` (``route_service``, ``retry_service``, ``budget_service``, ``limits_service``)."""
