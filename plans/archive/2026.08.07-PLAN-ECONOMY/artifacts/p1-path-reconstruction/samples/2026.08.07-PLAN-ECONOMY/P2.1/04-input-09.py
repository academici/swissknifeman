        budget = cls(same_finding_max=same_finding_max)
        plan_dir = Path(plan_dir)
        phase_path = plan_dir / "phases" / f"{phase_id}.md"
        try:
            phase_lines = phase_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return budget, "unknown"
