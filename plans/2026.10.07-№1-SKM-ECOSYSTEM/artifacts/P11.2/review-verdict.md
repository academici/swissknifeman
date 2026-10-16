# P11.2 review, round 1 (reviewer grok/grok-4.7, requested effort high)

Session: 01a12b49-adaa-70c0-9a8c-31e3e18a67fa (model grok-4.7 proven by updates.jsonl; the session record carries no effort or contextWindowTokens, no context capacity was requested). Stream: review-grok-round1.stream.jsonl. Verdict: FINDINGS (4, all suggestions, 0 bugs).

Executor confirmation by own run, one owning correction:
1. sessions --project used a different PARTNER_UNAVAILABLE sentence than scan — confirmed; registry_rows now always prints the scan sentence (design: same message).
2. projects-list/v1 rejected null local_path/vault_path of brain-fallback records — confirmed from map_brain_project; schema allows null, test added.
3. legacy project dirs covered only in test_lessons — confirmed; cases added to test_consolidation and test_recompute.
4. install_maind_stub lost to MAIND_BIN — confirmed; stub drops MAIND_BIN and SKM_MAIND_ROOT.
Re-run after correction: analyst 351 tests, maind 628, validate OK, standalone analyst pass, integration OK, public-hygiene 0.
