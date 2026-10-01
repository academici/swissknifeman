# RUN-FIXTURE — Fixture plan for the driver exec-waves (P4.2)

## 0. Meta

| Field | Meaning |
|:--|:--|
| Plan ID | RUN-FIXTURE |
| Title | Fixture plan for the driver exec-waves |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Last Updated | 2026-08-01 |
| Repository | swissknifeman |
| Related Packages | harness |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (design/audit) |
| Approval Owner | dv |

## 1. Context

Synthetic plan for unit tests `harness/run/plan_reader.py` (P4.2) —
is reused P4.3–P4.6. NOT a battle plan, does not participate in plan-fleet protocol.

## 2. Execution Rules

- One item at a time.

## 3. Routing

| Items | Model class/effort | Exec | Why |
|:--|:--|:--|:--|
| P1.1 | implementation/medium | run | single cell shape `Items` — basic drivable-case |
| P1.3–P1.5 | implementation/medium | run | single phase range shape - covers P1.3 (P1.4/P1.5 not in phase) |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/total | Status |
|:--|:--|:--|:--|
| P1 | Phase times | 1/3 | 🟡 In progress |

## 5. Decision Log

| D# | Date | Solution | Why |
|:--|:--|:--|:--|
| D1 | 2026-08-01 | Fixture with a closed set of forms §3 Routing | cover drivable/range without a second parser |

## 6. Update Log

| Date | Who (role/model) | What |
|:--|:--|:--|
| 2026-08-01 | package-implementer/sonnet | Fixture created (P4.2) |
