# HANDOFF — 2026-07-13 — after P2.2

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — P2.3 (`plan.md` §3 Routing: P2.1–P2.4 = opus/high,
Exec = manual; `/task:plan-exec` пинит sonnet/medium → по routing-гейту §9 обязан отказать,
`ROUTING-BLOCKED`. До появления `/task:plan-run` (item P3.5, D18) — только ручной запуск в
сессии, где уже выставлены `/model opus` + `/effort high`)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — item несёт ОБА SSOT сразу (канон §4/§11 + парсер и cross-plan сверка в `plan_lint.py`): схема секции, semver-сравнение, back-compat 26 планов, тесты. Инварианты + public contract → SSOT §9: high+ MANDATORY |
| Context | continue (/clear) — ручной item; items P2 делят `SKILL.ru.md`, строго последовательно |
| Суть | `## 7. Contracts` (Exported/Consumed) в §4 + cross-plan notification в §11 + парсер и сверка версий в `plan_lint.py` + тесты (m7/D10) |

````
Запусти вручную под opus/high (НЕ /task:plan-exec — Exec=manual): исполни item P2.3 плана
2026.07.13-PLAN-PROTOCOL-GAP по протоколу plan-exec (packages/skiller/skills/general/
plan-protocol/SKILL.ru.md §8–11) — прочитай plan.md (Context, Execution Rules, §3 Routing,
D-лог: D10 + новые D15–D19), phases/P2.md (Phase Context + item P2.3 целиком, включая
Completion Notes закрытых P2.1/P2.2), закрой item по каноническому порядку закрытия §8 (дифф
→ validate → bookkeeping → перезапись handoff → plan-lint --baseline HEAD ПОСЛЕ handoff →
коммит). Правило двух SSOT: `SKILL.ru.md` §4/§11 И `plan_lint.py` правятся В ОДНОМ item'е.
Гейт приёмки — back-compat: ноль НОВЫХ ERROR/WARNING по 9 корням флота (ни один живой план
секции 7 не имеет).
````

**Done:** P1 терминальна (`4c03715`, `b45cd51`). P2.1 🟢 (`38954ab`) — §9: канон-форма строки
Routing (колонка Exec), тир-порядок (`haiku < sonnet < opus ≈ fable`; `low < medium < high <
xhigh < max`), деривация Exec + консистентность заполненной колонки, routing-гейт из 5 веток
(`ROUTING-BLOCKED` / `ROUTING-INCONSISTENT`), back-compat легаси-форм. P2.2 🟢 — §6: status-rule
(непустые Known Deviations сами по себе статус не меняют; 🟠 — закрытый список из 5
material-триггеров; 🟢 при process + ОБЯЗАТЕЛЬНАЯ запись; недобор модели/effort вынесен из
предиката — он запрещён гейтом §9), «фазовая когерентность производного» (D17) и «дефект ТЗ ≠
отклонение исполнителя» (D19: эскалация → D# владельца → синк Scope → 🟢). Между фазами владелец
принял D18 (`fc57561`): новый item **P3.5** — команда `/task:plan-run` БЕЗ пина модели (наследует
сессию), чтобы manual-items не требовали ритуала `/model` + `/effort` + вставки промпта; жёсткий
гейт остаётся за `plan-exec`. Полные детали — `phases/P2.md` Completion Notes P2.1/P2.2.

**Remaining:** P2.3 (§4/§11 Contracts + парсер/сверка в `plan_lint.py` + тесты) → P2.4
(ТЕРМИНАЛЬНЫЙ item фазы: snippets + version 2.3.0 + **регенерация EN-канона** + `skiller registry`
— снимает красный `check-translations`) → P3 (5 items, sonnet/medium: `plan-exec` routing-гейт,
`plan-close`, `plan-audit`, `plan-design`, новый `plan-run`) → P4 (3 items — регресс по 9 корням
флота, закрытие эскалации REGHUB в чужом репо, доки/CHANGELOG).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, Execution Rules, §3
Routing, D-лог D1–D19) · `phases/P2.md` (Completion Notes P2.1/P2.2; ТЗ P2.3/P2.4) ·
`phases/P3.md` (ТЗ P3.1–P3.5) · `findings/P0-protocol-gap-recon.md` · SSOT-цели:
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` (§6, §9 — закрыты; §4/§11 — предмет
P2.3), `packages/task/lib/task/plan_lint.py`.

**Open risks:**
- P2.3 — единственный item фазы, трогающий КОД линтера: гейт приёмки = ноль новых ERROR/WARNING
  по 26 живым планам в 9 корнях (Execution Rules). Регресс-прогон обязателен ДО коммита.
- Фаза P2 правит SSOT-канон: формулировки = public contract для флота. Ревью P2.1 показало, что
  дефекты бывают в САМИХ формулировках ТЗ (D15/D16) — ТЗ не заменяет думанье, читать критически.
- EN-канон `SKILL.md` протух намеренно (D17, теперь канонизировано в §6) →
  `packages/skiller/scripts/validate.sh` красный на `check-translations` до P2.4. Это ожидаемо,
  не регресс; в P2.4 снимается регенерацией.
- Routing-гейт §9 и status-rule §6 уже в SSOT, но в текстах команд `/task:plan-*` их ещё НЕТ (P3):
  до P3 правила исполняет только читающий человек/агент.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: регенерация EN-канона (P2.4, D17); миграция §3 Routing 26 живых планов на канон-форму
  с колонкой Exec (back-compat: легаси-формы валидны); кросс-репо push-уведомление о bump'е
  контракта (роадмап, вне scope).
- open_questions: развилки `plan.md` §Обсуждение (авто-делегация в Workflow, релакс ERROR→WARNING
  на скелетах) — отклонены D-логом; возражение владельца перебивает новым D# со `supersedes`.
