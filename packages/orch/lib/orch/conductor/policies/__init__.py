"""The rules of a run: routes, limits, retries, the sandbox, the risk score, prompt budgets and skill checks.

A rule that needs nothing of the run is a plain function with explicit arguments; one that reads or records the run
takes the conductor (``self``) and is bound as its method in ``engine.py``."""
