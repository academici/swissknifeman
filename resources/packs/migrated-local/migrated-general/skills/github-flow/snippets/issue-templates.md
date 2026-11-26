# Issue Templates for .github/ISSUE_TEMPLATE/

## bug_report.md

```markdown
---
name: Bug report
about: Something is broken
labels: ["bug", "needs-triage"]
---

## Summary
<!-- [bug] header ≤72 characters, imperative -->

## Affected version
<!-- Package version where played -->

## Steps to reproduce
1.

## Expected behavior

## Actual behavior

## Environment
- PHP / runtime version:
- Framework version:
```

## feature_request.md

```markdown
---
name: Feature request
about: New capability or enhancement
labels: ["enhancement"]
---

## Problem
<!-- What user problem does this solve -->

## Proposed solution
<!-- Wishful API/behavior, example code -->

## Alternatives considered

## Breaking change?
<!-- Will an existing public API -->
```

## config.yml (disable empty Issues)

```yaml
blank_issues_enabled: false
contact_links:
  - name: Security vulnerability
    url: https://github.com/<owner>/<repo>/security/advisories/new
    about: Do not open public Issue for vulnerabilities
```
