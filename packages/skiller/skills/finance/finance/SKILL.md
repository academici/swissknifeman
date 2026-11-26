---
name: finance-super-skill
bucket: finance
version: 1.0.0
description: Finance and accounting: financial statements, journal entries, reconciliation, close management, audit support, variance analysis, market data, investment research, ML forecasting, invoice processing. Use for financial reporting, month-end close, audit prep, variance analysis, market research, investment thesis, or finance data work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Finance & Accounting Super-Skill — Navigator

Thin navigator over the vendored **get-zeked/finance-super-skill**. The full reference
(13 sections + 2 appendices: templates, checklists, code) is in
[`references/full.md`](references/full.md). **Open it point-blank for the specific
question — jump to the section below, never load the whole file.**

## Section map (`references/full.md`)

| Task | Section |
|:--|:--|
| Capability overview: which sub-skill covers what | [§0 Gap Analysis](references/full.md#0-gap-analysis-perplexity-computer-vs-claude-code-finance-skills) |
| IS/BS/CF templates, ratios, DCF, industry KPIs | [§1 Financial Statements](references/full.md#1-financial-statements--reporting) |
| Debits/credits, JE templates, accrual checklist | [§2 Journal Entries](references/full.md#2-journal-entries--transaction-processing) |
| Bank/GL/intercompany recs, BS substantiation | [§3 Reconciliation](references/full.md#3-account-reconciliation) |
| Close calendar, task tracker, dependencies | [§4 Month-End Close](references/full.md#4-month-end-close-management) |
| Waterfall, driver-based commentary | [§5 Variance Analysis](references/full.md#5-variance-analysis--commentary) |
| PBC lists, control testing, sampling, SOX | [§6 Audit Support](references/full.md#6-audit-support--sox-compliance) |
| Quotes, historicals, SEC data, investment thesis | [§7 Markets & Research](references/full.md#7-markets--investment-research) |
| ETL/ELT pipelines, warehouse models, dbt/Airflow | [§8 Data Engineering](references/full.md#8-data-engineering-for-finance) |
| Forecasting, anomaly detection, ML models | [§9 ML & Forecasting](references/full.md#9-ml--forecasting-for-finance) |
| Invoice extraction, naming, folder taxonomies | [§10 Invoices & Documents](references/full.md#10-invoice--document-management) |
| Perplexity Computer-only tooling | [§11 Unique Capabilities](references/full.md#11-unique-perplexity-computer-capabilities) |
| "Which section do I need?" fast router | [§12 Quick-Start Guide](references/full.md#12-quick-start-decision-guide) |
| Chart of accounts, normal balances | [App. A](references/full.md#appendix-a-financial-accounts-quick-reference) |
| Abbreviations (GAAP, EBITDA, DSO, ...) | [App. B](references/full.md#appendix-b-common-financial-abbreviations) |

## Maintenance

Upstream-tracked (`strategy: notify`, `body_path: references/full.md`): this SKILL.md is
hand-written; on drift (`scripts/update-upstreams.sh --check`) port changes into `references/full.md`.
