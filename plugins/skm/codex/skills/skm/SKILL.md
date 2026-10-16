---
name: skm
description: swissknifeman front door — project skills, integration, status and diagnostics through the swissknifeman and skiller CLIs.
---

Use the installed CLIs, never edit their state by hand:

- skills of the project: `skiller status`, `skiller connect --plugins <buckets>` or `skiller vendor`;
- full integration (skills, hooks, permissions, memory, hub): `skiller integrate --dry-run`, then `--yes`;
- diagnostics of every module: `swissknifeman doctor` (`--json` for the `umbrella-doctor/v1` document).
