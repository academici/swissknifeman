# HANDOFF — 2026-07-13 — after P2.3

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — P2.4 (`plan.md` §3 Routing: P2.1–P2.4 = opus/high,
Exec = manual; `/task:plan-exec` пинит sonnet/medium → routing-гейт §9 обязан отказать,
`ROUTING-BLOCKED`). **Терминальный item фазы P2**: снимает красный `check-translations`
(D17 — фазовая когерентность производного)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — регенерация EN-канона: агент грузит ТОЛЬКО `SKILL.md`, поэтому качество компактного EN = качество канона для всего флота; плюс контроль бюджета тела (≤620 строк) и сверка, что все четыре новых правила доехали |
| Context | continue (/clear) — ручной item; последний item фазы P2 |
| Суть | snippets (plan/handoff/launch-block) + version 2.3.0 + **регенерация `SKILL.md` из RU** + `check-translations.sh --stamp` + `skiller registry` |

````
Запусти вручную под opus/high (НЕ /task:plan-exec — Exec=manual): исполни item P2.4 плана
2026.07.13-PLAN-PROTOCOL-GAP по протоколу plan-exec (packages/skiller/skills/general/
plan-protocol/SKILL.ru.md §8–11) — прочитай plan.md (Execution Rules, §3 Routing, D-лог:
D12 + D15–D20), phases/P2.md (item P2.4 целиком + Completion Notes закрытых P2.1–P2.3),
закрой item по каноническому порядку закрытия §8 (дифф → validate → bookkeeping →
перезапись handoff → plan-lint --baseline HEAD ПОСЛЕ handoff → коммит). Порядок работ
СТРОГИЙ: RU → snippets → version 2.3.0 → регенерация SKILL.md промтом
packages/skiller/prompts/generate/claude-canon-from-ru.md → check-translations.sh --stamp
→ skiller registry. Править SKILL.md руками ЗАПРЕЩЕНО. После item'а
`bash packages/skiller/scripts/validate.sh` обязан стать ЗЕЛЁНЫМ — это гейт закрытия фазы
(D17: полный зелёный требуется на терминальном item'е). Фазу P2 после этого закрывает
/task:plan-close 2026.07.13-PLAN-PROTOCOL-GAP P2.
````

**Done:** P1 терминальна (`4c03715`, `b45cd51`). P2.1 🟢 (`38954ab`) — §9: канон-форма строки
Routing (колонка Exec), тир-порядок, деривация + консистентность Exec, routing-гейт
(`ROUTING-BLOCKED` / `ROUTING-INCONSISTENT`). P2.2 🟢 (`cd749ab`) — §6: status-rule (5
material-триггеров; 🟢 при process + обязательная запись), «фазовая когерентность производного»
(D17), «дефект ТЗ ≠ отклонение исполнителя» (D19). P2.3 🟢 — оба SSOT синхронно: `SKILL.ru.md`
§4 (опциональная `## 7. Contracts`, две подтаблицы) + §11 (cross-plan notification: обязанность
несёт ITEM, связь строится ОТ потребителя, кросс-репо граница названа честно) и `plan_lint.py`
(`parse_contracts`, модель `contracts` в `--json`, root-сверка `Pinned` ≠ `Версия` донора →
WARNING; +5 тестов, 104 → 109 зелёных). Регресс по 9 корням флота: **0 новых ERROR, 0 новых
WARNING** — и он же поймал дефект ТЗ (жёсткая привязка секции к номеру 7 давала 2 новых WARNING
планам, уже занявшим этот номер) → D20: секция опознаётся по ЗАГОЛОВКУ. Между фазами владелец
принял D18 (`fc57561`) → новый item **P3.5** (`/task:plan-run` — команда без пина модели).
Полные детали — `phases/P2.md` Completion Notes P2.1–P2.3.

**Remaining:** P2.4 (терминальный item фазы) → закрытие фазы P2 (`/task:plan-close … P2`) → P3
(5 items, sonnet/medium: `plan-exec` routing-гейт, `plan-close`, `plan-audit`, `plan-design`,
новый `plan-run`) → P4 (3 items — регресс по флоту, закрытие эскалации REGHUB в чужом репо,
доки/CHANGELOG).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, Execution Rules, §3
Routing, D-лог D1–D20) · `phases/P2.md` (Completion Notes P2.1–P2.3; ТЗ P2.4) · `phases/P3.md`
(ТЗ P3.1–P3.5) · SSOT-цели: `packages/skiller/skills/general/plan-protocol/SKILL.ru.md`
(§4/§6/§9/§11 — закрыты; frontmatter version + snippets + EN-канон — предмет P2.4),
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- P2.4 — единственный item, который трогает `SKILL.md` (EN-канон): править его РУКАМИ запрещено,
  только регенерация промтом. Агенты флота грузят ТОЛЬКО EN — ошибка регенерации = правила фазы
  P2 не доедут до исполнителей вовсе.
- Бюджет тела EN-канона: ориентир ≤620 строк (RU вырос на ~90 строк за фазу). Раздулось сильнее —
  ужимать формулировки, а не «оставить как вышло»: скилл в CORE, грузится во всех проектах флота.
- До P2.4 `packages/skiller/scripts/validate.sh` красный на `check-translations` (D17, ожидаемо).
  После P2.4 обязан быть зелёным — иначе фаза P2 не закрывается.
- Правила §6/§9/§11 уже в SSOT, но в текстах команд `/task:plan-*` их ещё НЕТ (фаза P3): до неё
  routing-гейт и status-rule исполняет только читающий человек/агент, автоматически — никто.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: миграция §3 Routing 26 живых планов на канон-форму с колонкой Exec (back-compat:
  легаси-формы валидны); заполнение секции `## 7. Contracts` в живых планах (REGHUB — P4.2);
  кросс-репо push-уведомление о bump'е контракта (роадмап, вне scope).
- open_questions: развилки `plan.md` §Обсуждение (авто-делегация в Workflow, релакс ERROR→WARNING
  на скелетах) — отклонены D-логом; возражение владельца перебивает новым D# со `supersedes`.
