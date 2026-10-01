# Fixture plan

Synthetic plan tree (`DEMO-PLAN`) read by the artifex tests. Admission carriers and grants are rebuilt with the package's own `dispatch.canonical_hash`, `dispatch.project` and `dispatch.file_hash`; never hand-edit a digest — change the content and recompute through those functions. The mandate source pins hold the sha256 of their path strings.
