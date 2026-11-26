# Step 1. Repo Structure

Skill reference `oss-development`.


Standard structure OSS-repository:

```
ProjectName/
├── src/                    # Source code
│   └── index.ts            # Entry point
├── tests/                  # Tests
├── docs/                   # Documentation (if large)
├── examples/               # Examples of use
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/          # CI/CD
├── README.md               # Main document
├── CONTRIBUTING.md         # How to contribute
├── CHANGELOG.md            # Revision history
├── LICENSE                 # Required
└── package.json / go.mod / Cargo.toml
```

---
