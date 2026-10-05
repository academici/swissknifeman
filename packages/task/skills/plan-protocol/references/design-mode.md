# Design mode

Goal: an item that a weaker model can execute from `context/<item>.json` alone.

1. Start from evidence: read the code the item will change and the owner's brief; stop researching
   once implementation choices and acceptance are clear.
2. One item = one reviewable outcome. Use the items and reads needed for a self-contained contract. No read quota.
3. Every detailed item carries: `summary`, `why`, `scope.include/exclude`, `reads` (path, optional
   `section`, why, required), `task_files`, `rules`, `guidance`, `validation` (exact commands,
   `kind: acceptance`), `deliverables`, `route`, `authority`, `depends_on`/`related`.
4. Put long reasoning, algorithms and worked examples in JSON `sections` or `knowledge/<id>.json`
   through `add-document`, and reference the section id from `reads` or `examples`.
5. Open questions become decisions (`add-decision`); an item that relies on one names it in
   `decisions`. Accept with `decide` and a rationale.
6. Detail one phase at a time when later phases depend on real code; `design-done` only after
   `plan.py check` reports 0 errors.
7. Design never executes items and never adds review items unless `--review` or the owner asks.
