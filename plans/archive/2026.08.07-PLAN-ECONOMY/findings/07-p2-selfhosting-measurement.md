# P2.8 self-hosting measurement — 2026-08-08

## What and when

The v1→v2 converter migrated `2026.08.07-PLAN-ECONOMY` in place after a read-only dry run.
It inventoried 1,053 legacy elements across all 45 items and then measured every mandatory
read path with `packages/task/scripts/plan-weight.py`.

## Tool and calibration

The measurement uses `token-estimate-calibration` v2.0.0 for `codex/gpt-5.6-terra`, the
qualified unit frozen by `read-budget` v1. The acceptance threshold is 100,000 estimated input
tokens per item.

## Coverage

All 45 item IDs from `artifacts/p2-migration-inventory.json` were measured before and after.
The inventory records `missing: []`; 16 Meta fields were checked by name, including `Design Passes`
and `visibility`.

## Before/after distribution

The aggregate mandatory-read estimate fell from 7,089,706 to 2,263,520 tokens. Median item weight
fell from 140,855 to 33,003 tokens. These figures come from
`artifacts/p2-weight-before-after.json`.

## Threshold result

Four items remain above the frozen threshold: `P2.1`, `P3.6`, `P6.5`, and `P6.9`. Acceptance is
therefore blocked: changing the threshold or silently shortening a read path would change D2/D17
and requires an owner-approved redesign.

## What this does not prove

This is one self-hosted plan, not a fleet distribution or proof that a future plan can stay below
the budget. The converter's dry-run safety and this result do not authorize migration of another
plan.
