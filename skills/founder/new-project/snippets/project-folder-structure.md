# Project Folder Structure

```
ProjectName/
├── ProjectName.md              # control tower: frontmatter contract + status + links
├── Открытые вопросы.md         # open questions, created empty
│
├── docs/                       # ALL project documentation
│   ├── 01_Business/            # concept, competitive analysis, risks, unit economics, GTM
│   ├── 02_Workflow/            # business processes, FSM, glossary
│   ├── 03_Dev/                 # BRD, architecture, DB schema, API, ADR/
│   ├── 04_Execution/           # roadmap, backlog (optional)
│   ├── 05_AI/                  # project-level AI context: skills/, guidelines/
│   └── shared/                 # mirror of code-repo docs/ (synced, standard Markdown only)
│
└── assets/                     # binaries: docx, images, archives
```

Frontmatter contract for `ProjectName.md`:

```yaml
---
type: project
status: concept | active | paused | archived
category: startup | oss | business | freelance
tags: [<project-slug>, <domain>]
uses: []          # vault projects this depends on
used_by: []       # vault projects depending on this
repo:             # path to code repo (optional)
repo_docs:        # path to repo docs/ — enables docs/shared sync
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

OSS variant: no `01_Business`/`02_Workflow`; `docs/shared/` is the primary
documentation (mirrored from the repository), `docs/03_Dev/` for internal notes.
