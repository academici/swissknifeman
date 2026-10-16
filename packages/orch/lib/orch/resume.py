"""Resume guard: a run may only continue on the inputs its launch-plan was prepared from (invariant I8)."""
from __future__ import annotations

# Drift name -> where the launch-plan recorded the value it was prepared with.
CHECKED = (("input", ("digests", "input")), ("policy", ("digests", "policy")), ("roles", ("digests", "roles")),
           ("config", ("digests", "config")))


def verify_resume(plan: dict, *, input_digest: str, policy_digest: str, roles_digest: str, config_digest: str,
                  binding: str) -> list[str]:
    """Names of the inputs that differ from the launch-plan, in the order input, policy, roles, config, binding.

    An empty list means resume is allowed; otherwise the caller refuses with ``RESUME_REFUSED`` and
    ``data.drift`` set to the list. A launch-plan without the recorded value counts as drifted: its history cannot
    be reinterpreted against inputs it never recorded.
    """
    current = {"input": input_digest, "policy": policy_digest, "roles": roles_digest, "config": config_digest}
    drift = []
    for name, (section, key) in CHECKED:
        recorded = plan.get(section)
        if not isinstance(recorded, dict) or recorded.get(key) != current[name]:
            drift.append(name)
    if plan.get("binding") != binding:
        drift.append("binding")
    return drift
