# Design audit — 2026.07.19-DUAL-PROVIDER — заход 3

**Дата:** 2026-07-19  
**Режим:** повторный adversarial design audit r3 после remediation audit-r2 F1  
**Вердикт: RED**

## Anchor и plan-lint

- `HEAD`: `9844f499797faf063aede49b79703c71f7ef666e`.
- Audit-input worktree snapshot до разрешённых audit writes:
  `sha256:92da915766507cdb4c27aa03728d09036205010b14b95b008b3b8300cbcf8c04`.
  Команда: `find plans/2026.07.19-DUAL-PROVIDER -type f -print0 | LC_ALL=C sort -z |
  xargs -0 sha256sum | sha256sum`.
- Remediation lint-input snapshot из verification finding воспроизведён точно:
  `sha256:3a3f6284f8e5cdd72061ab119af8f573cf97eef83e874c2ae7833b9dd586edfb`;
  toolchain snapshot —
  `sha256:998d3e3f5d98ce89f700e00d817e8a28319f47f9b464c71d653d3b7a0efa36e9`.
- Post-journal lint-input snapshot, исключающий только этот audit-report carrier:
  `sha256:8b99b03b2eaf3b669eac7ac5a8781a9ddcfc819c532a150d719fd545cb690289`.
- `journal.jsonl:11` без newline:
  `sha256:94307a3c3bfaf4c5d5d67ea32d8eacb09410a396b0a217ab2eb094b518693184`;
  sidecar несёт тот же hash, `target_line:11` и `invalid_fields:["friction"]`.
- Команда: `python3 packages/task/scripts/plan-lint.py
  plans/2026.07.19-DUAL-PROVIDER`. До и после terminal audit append результат один:
  **0 ERROR / 0 WARN**, exit code `0`. Это доказывает current scoped schema gate, но не
  опровергает adversarial fail-open finding ниже.

## Findings

### F1 — same-plan invariant sidecar не гейтится и fail-open

- **Severity:** Major
- **Label:** issue
- **Item:** design / journal historical schema exception
- **Evidence:** `research/14-journal-schema-exception-remediation.md:40-46`;
  `packages/skiller/skills/general/plan-protocol/SKILL.md:76-80`;
  `packages/task/lib/task/journal.py:187-229`;
  `packages/task/lib/task/plan_lint.py:758-800,826-839`;
  `packages/task/tests/test_journal.py:135-195`;
  `packages/task/tests/test_plan_lint.py:137-189`.
- **Failure scenario:** contract/canon требуют, чтобы target event принадлежал текущему
  плану. Writer сравнивает только `target.plan_id == exception.plan_id`; linter принимает
  аргумент `plan_id`, но не передаёт/не сверяет его с target/sidecar. Независимый temp-root
  probe создал каталог плана `2026.07.18-DEMO`, event с
  `plan_id="2026.07.18-OTHER"` и единственной schema-ошибкой `friction`, затем matching
  D51-sidecar с тем же foreign ID. Фактический результат `lint_plan`:
  `wrong-plan probe errors: 0`, `wrong-plan probe warnings: 0`. Поэтому ошибочно
  скопированная/смёрженная foreign event-строка может получить исключение и пройти зелёный
  gate, хотя опубликованный contract обещает fail-closed «того же плана» provenance.
- **Требуемая remediation:** связать event и exception с canonical ID текущего plan
  directory в writer и linter; plan-ID mismatch должен оставаться non-exemptable ERROR и не
  подавляться sidecar. Добавить отдельные writer+linter negative tests на foreign event ID,
  foreign sidecar ID и точное error-field множество; затем воспроизвести current `0/0` и
  wrong-plan nonzero. P0.1 не запускать.

## Проверено без находок

- Фактическая D51-запись этого плана корректна: D51 существует в Decision Log;
  row 11 bytes/hash сохранены; независимая проверка дала ровно одно invalid field —
  `friction`; sidecar имеет ровно восемь разрешённых полей и не несёт
  `item_id/command/result/status/next/session_id/run_id`.
- Sidecar структурно ацикличен: target задаётся только физической строкой sibling
  `journal.jsonl`; path/sidecar target/correction chain в schema отсутствуют. Hash mismatch,
  duplicate, missing D#, already-valid target, unknown sidecar fields и malformed JSON
  остаются error paths; единственный найденный fail-open — отсутствие binding к current plan ID.
- Writer/schema/linter/lifecycle согласованы по additive surface; sealed event enums/14
  полей не изменены. `task` получил SemVer `0.1.0→0.2.0`, `plan-protocol` —
  `2.9.0→2.10.0`; EN/RU canon и journal template синхронны.
- Targeted tests: **32/32 OK**; full task suite: **186/186 OK**; strict translation gate:
  `160` local skills, `0` stale/missing EN markers, `0` lost literals; `git diff --check` = 0.
- Регрессии r2 non-F1 areas не найдены: **39/39** items, каждый с ровно 16 полями и
  `⬜ Not started`; Routing **39/39** (`11 plan-exec`, `28 manual`); execution-map roadmap
  **39/39 unique**. P5.6→P5.7 instruction producer order, P6.2/P6.5/P6.6 integration/restart
  carriers и P7 consumer-only boundary сохранены.
- P0.1 остаётся закрыт: `phases/P0.md:34,41` = `⬜ Not started`; roadmap разрешает его
  только после literal GREEN design audit (`roadmap.md:93-104`). Этот r3 verdict RED, поэтому
  execution не начинается.
- `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`, fleet, package files/items,
  instruction remediation P5.6→P7 и unrelated user changes этим audit не изменялись.

## Что запускать

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high |
| Context | NEW SESSION — шаг-не-item |
| Суть | Точечно закрыть same-plan fail-open historical exception и вернуть plan в повторный audit |

```
$ task:plan-design 2026.07.19-DUAL-PROVIDER finish

РЕЖИМ: точечная remediation design audit r3, НЕ execution
ВХОД: plans/2026.07.19-DUAL-PROVIDER/findings/design-audit-2026-07-19-r3.md → F1; прочитать ПЕРВЫМ
СКОУП: 1) связать event+exception plan_id с canonical ID текущего plan directory в writer и linter 2) сделать mismatch non-exemptable ERROR и добавить writer/linter negative tests для foreign event/sidecar IDs + exact field-set 3) синхронизировать lifecycle canon/research/D# только если меняется contract и воспроизвести current 0 ERROR / 0 WARN + wrong-plan nonzero 4) подготовить новый design audit без запуска P0.1
НЕ ТРОГАТЬ: P0.1–P7.4 implementation/items; package seams вне task journal/linter/tests и plan-protocol journal lifecycle; plans/2026.07.18-FOREMAN/**; plans/ACTIVE.md; fleet; instruction remediation P5.6→P7; unrelated user changes
```
