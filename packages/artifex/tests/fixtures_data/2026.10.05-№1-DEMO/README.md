# Fixture plan

Synthetic v3 plan (`2026.10.05-№1-DEMO`) read by the artifex tests. The JSON and the generated views were written only through `support.make_plan` (`plan.py new/set/add-phase/add-item`); never edit them by hand, regenerate with that helper. `artifacts/` holds the contract fixtures. Admission carriers and grants are rebuilt with the package's own `dispatch.canonical_hash`, `dispatch.project` and `dispatch.file_hash`; never hand-edit a digest — change the content and recompute through those functions. The mandate source pins hold the sha256 of their path strings.
