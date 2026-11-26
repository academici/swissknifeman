+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "result_contract"
variables = ["role.result_schema"]
+++
## Result

End your session with exactly one JSON document and nothing after it. It must match the schema
`{{ role.result_schema }}`:

```json
{
  "schema": "{{ role.result_schema }}",
  "verdict": "attention",
  "summary": "Core rotation logic holds, but expiry uses local process clock instead of database time.",
  "findings": [
    {
      "id": "F1",
      "severity": "major",
      "confidence": "high",
      "basis": "correctness",
      "category": "time_handling",
      "message": "Expiry is compared against process wall time instead of database transaction time.",
      "failure_scenario": "A node with a lagging clock accepts and rotates an already expired refresh token.",
      "location": {
        "mount": "repo",
        "path": "src/auth/rotation.py",
        "line_start": 41,
        "line_end": 44
      },
      "reproduction": {
        "argv": ["python", "-m", "pytest", "tests/auth/test_rotation.py", "-k", "expiry", "-q"],
        "expected_exit": 1
      },
      "fix_hint": "Compare expires_at against database now() inside the locking SELECT."
    }
  ],
  "residual_risk": "High-contention parallel refresh load was checked structurally via FOR UPDATE, not benchmarked.",
  "coverage": {
    "paths_reviewed": ["repo:src/auth/rotation.py", "repo:tests/auth/test_rotation.py"],
    "criteria_checked": ["AC1"]
  }
}
```

- `verdict`: `green` (no `blocker` or `major` findings; `findings` is empty or holds only `minor`/`nit`),
  `attention` (at least one finding requiring triage), or `red` (contract or safety failure; at least one finding).
- `findings`: each item has local id `F<n>`, `severity` (`blocker | major | minor | nit`), `confidence`
  (`high | medium | low`), `basis` (`correctness | security | contract | test | maintainability | docs`),
  `category` (`snake_case` or `domain/subtopic`), `message`, `failure_scenario`, `location` (`mount`, `path`,
  optional `line_start`, `line_end`), and optional `reproduction` (`argv`, `expected_exit`) and `fix_hint`.
- `residual_risk`: non-empty statement of remaining unverified risk even when `verdict` is `green`.
- `coverage`: optional summary of reviewed paths and checked acceptance criteria (`AC<n>`).
