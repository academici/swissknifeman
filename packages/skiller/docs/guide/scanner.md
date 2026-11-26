# Snippet scanner

Scanner extracts snippet candidates from local projects - real code
from real practice, not fictitious examples. Project paths are listed
in `.skills-scanner.json`.

## Pipeline

```bash
# 1. Find candidates in listed projects
./scripts/scan-skills.sh

# 2. Extract and anonymize to .scanner-output/
./scripts/scan-skills.sh --extract

# 3. Commit and open PR
./scripts/scan-and-pr.sh
```

`.scanner-output/` in `.gitignore` — extraction results are added to the repository
only via PR after the review.

## Algorithm

```
SCAN   → find files by patterns (*.php, Dockerfile*, *.yml)
FILTER → remove vendor/, generated code, trivial snippets
SCORE  → evaluate according to quality criteria
MATCH  → determine the target skill along the path/context
DEDUPE → check that such a snippet is not yet in the registry
CREATE → create a file in skills/{bucket}/{skill}/snippets/
UPDATE → update snippets/index.json
COMMIT → git commit + PR
```

## Snippet quality criteria

The selection threshold is set in `.skills-scanner.json` (`quality_threshold: 60`).
Rating out of 100:

| Criteria | Weight |
|---|---|
| Solve a real problem (not hello world) | 30 |
| Current Practices (PHP 8.2+, typed properties) | 20 |
| There are comments or docblock | 20 |
| Length 10–100 lines (optimal) | 10 |
| No hardcoded-values | 10 |
| Can be used without modification | 10 |

The same criteria apply to reviews PR from scanner: candidate below threshold -
is rejected or modified before merging.

## Automation

Workflow `scanner-pr.yml` runs the scanner weekly and opens PR with new
candidates. The scan paths are local projects: on a hosted runner none exists and the scan says
`SCAN_PATHS_ABSENT`; run `./scripts/scan-and-pr.sh` on the machine that has them. A scanner error fails the job. The decision on what will become a skill snippet from what is found is up to the reviewer.

## Why is this needed

The best snippets are those that have already worked in battle. The scanner closes the loop:

```
real project → scanner → PR → review → snippets/ skill → new project
```

So the developments from AzGuard, botkit and other projects are gradually becoming
into reused skills.
