# HANDOFF — 2026-07-25 — after P4

`P4` в заголовке — совместимый с plan-lint lifecycle carrier для repair-прохода
Owner authority C; executable phase P4 и все 21 items остаются ⬜ Not started.

**Next:** audit-design: task:plan-audit 2026.07.24-AGENT-RELIABILITY design

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | — |
| Context | cold-start — plan-step |
| Суть | A1 — единственный authority-C independent design audit после repair F1–F3; любой verdict останавливает сессию на Owner |

````
/task:plan-audit 2026.07.24-AGENT-RELIABILITY design

РЕЖИМ: independent design audit A1 (D32, слот 0/1) — adversarial, свежий контекст; НЕ repair, НЕ exec
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/findings/09-design-audit-exceptional-attempt-3.md (три находки) → сверить с repair v1.7.0: phases/P1.md P1.1/P1.2/P1.3, phases/P2.md P2.2/P2.3, phases/P3.md P3.4, plan.md D32–D34, roadmap.md
СКОУП: 1) проверить, что F1 (ITEM_BASE_SHA), F2 (same-item Required Reads), F3 (bootstrap-map gate) закрыты детерминированно; 2) полный DoR-свип 21 item; 3) literal-вердикт `**Вердикт: …**`
НЕ ТРОГАТЬ: сами packages/runtime; исторические Codex-блоки roadmap (projections); исчерпанные слоты аудитов B; FOREMAN
````

**Done:** Owner authority C (D32, `brief/02-claude-takeover.md`): bounded repair
трёх находок attempt 3 выполнен в v1.7.0 — F1: item baseline
`artifacts/<Pn.m>/base-sha.txt` (D34) определяет `ITEM_BASE_SHA` в P1.2/P1.3/
P2.2/P2.3; F2: self-produced артефакты убраны из Required Reads P2.3
(`review_policy.py`) и P3.4 (`canary-cases.json`) с явной пометкой; F3: P1.1
получил детерминированный гейт `--check-bootstrap-map` (13 identities, ключи,
seed-хеши, resolution). Acting provider переведён на Claude (D33): Meta,
Execution Rules, roadmap-шапка и Карта (21 строка → Claude opus/sonnet),
Codex-блоки понижены до historical projections. Кода пакетов не менялось.

**Remaining:** A1 audit (launch-block выше) → при GREEN — Owner `G-EXEC` →
P0.1 по roadmap. 21/21 items ⬜.

**Sources of truth:** `plan.md` v1.7.0 (D29–D34, §10 boundaries) ·
`phases/P0–P4.md` · `roadmap.md` (Claude-рендеринг) ·
`findings/09-design-audit-exceptional-attempt-3.md` ·
`brief/02-claude-takeover.md` · `journal.jsonl`.

**Open risks:** аудит A1 может найти новые дефекты — слот один, non-GREEN
возвращает Owner decision; sed-замена модель-колонки roadmap могла задеть
только Карту (проверено: renderer-таблица и Codex-блоки нетронуты); рабочее
дерево несёт чужой незакоммиченный дифф (архив-переносы старых планов + tmp/)
— не трогать.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: все 21 executable items (до A1 GREEN + G-EXEC);
- open_questions: — (судьба плана решена D32: keep + Claude).
