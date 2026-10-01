---
description: "Check the change for data leaks, authorization bypass, mass assignment, raw SQL — only real risks"
---
Check the change for: data leakage through responses/props, bypass Policy/Gate, mass assignment, raw
SQL, secret leak/credentials. List only real risks with ways to correct them - without general ones
lists OWASP.
<!-- pack:if SCAFFOLDS_SCHEMA -->
Special attention - `$fillable`/`$guarded` new models and protection of fresh migrations (indexes,
foreign keys, nullable default).
<!-- pack:endif -->
