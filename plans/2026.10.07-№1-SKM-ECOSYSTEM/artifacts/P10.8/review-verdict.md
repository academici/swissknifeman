# P10.8 review verdict

Reviewer: grok/grok-4.7/high, headless, read-only (launch through the orch bridge `launch`, role reviewer).
Session: 01a12914-f2b7-7ff2-a623-bc37b2cfca55 (grok `summary.json`: current_model_id grok-4.7, reasoning_effort high;
`signals.json`: contextWindowTokens 500000). Round 1 of at most 2; the reviewer returned 4 findings.

| # | Finding | Executor reproduction | Outcome |
| --- | --- | --- | --- |
| 1 | launch-plan bytes depend on the process working directory (`capability_ref`, `prompt_ref`) | confirmed: from another directory the refs differ; also `_path` was fixed at load time, a real defect | fixed: `_path` is absolute and made relative at prepare time; the working directory is documented as an input (engine-port.md) and pinned by `test_paths_are_relative_to_the_working_directory` |
| 2 | staleness ignored the fraction of a second | confirmed: `is_stale` False for fresh_until .100 and now .900 | fixed: `_moment` keeps microseconds; `test_a_fraction_of_a_second_counts` |
| 3 | an empty skill list of the manifest role fell through to the policy role | confirmed from the code and the reviewer's test | fixed: key presence decides; `test_an_empty_list_of_the_manifest_role_does_not_fall_through` |
| 4 | malformed `--skills` raised AttributeError/TypeError | confirmed: `[]` and `{"executor": [1]}` | fixed: `check_skills` in the CLI and `prepare_common` gives INPUT_INVALID; tests in test_prepare_proof and test_cli_prepare |

All four are fixed by one executor correction; V1, V2, V3 rerun green. No second review round was requested.
