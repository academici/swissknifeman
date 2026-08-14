# Recon — `2026.08.02-PROVIDER-CONTRACT-LOCALE P1` recovery

**Источник:** read-only repository reproduction, 2026-08-14.
**Evidence:** RAG:— (repo-grounded).

## Current committed facts

- Repository HEAD на момент recon: `b6d64d5c5fd16509915a66b4daa0345fb58c56ba`.
- `packages/task/**` и target-plan tree чисты относительно HEAD; dirty paths — чужие
  roadmap drafts.
- `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/journal.jsonl`, line 97:
  `item_id="P1 — режим фазы"`, `result="audit-green"`, fingerprint
  `7ce1e79c9c9ed40e325b7489ea01cf5dc0ee607f3425b91f674f7ac853c40b92`.
- Recomputed current candidate имеет тот же fingerprint, three `🟢 Done` heads и
  `material_risks=[]`.
- Current close gate возвращает `PHASE_AUDIT_MISSING` только из-за literal subject
  comparison. Task Contract ошибочно считает audit rounds равными нулю.

## Safe recovery contract

1. После Slice A повторно построить candidate и потребовать exact `7ce1…`.
2. `phase_close_gate()` должен вернуть `allow`, `journal_line=97`, reused `audit-green`.
3. Не запускать `task:plan-audit` и ни одну Validation P1.1–P1.3.
4. Выполнить ровно `task:plan-close 2026.08.02-PROVIDER-CONTRACT-LOCALE P1`.
5. После close normalized phase-audit count остаётся 1; после line 97 нет
   новых P1.1–P1.3 events; добавлен один `P1/plan-close` event.

## Hazards

- Не менять target P1 item specs, contracts, checker/fixtures, index и terminal evidence.
- `bundle --all --check` красен на future P2 input; recovery проверяет только P1 bundles.
- Unrelated roadmap drafts не попадают в closure commit.
