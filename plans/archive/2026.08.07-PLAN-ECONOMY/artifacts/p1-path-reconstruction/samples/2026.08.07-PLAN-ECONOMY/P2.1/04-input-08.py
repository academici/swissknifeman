    phase_token = item_id.split(".")[0]
    diag = plan_lint.Diagnostics()
    plan_lint.parse_plan_md(plan_dir / "plan.md", diag)  # populates diag only; not consulted here
    phase_path = plan_dir / "phases" / f"{phase_token}.md"
    phase = plan_lint.parse_phase_md(phase_path, phase_token, diag)
    occurrences = phase["items"].get(item_id) if phase else None
    if not occurrences:
        raise TaskContractBuildError(item_id, "item", f"no item block found in {phase_path}")
