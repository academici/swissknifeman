# HANDOFF — 2026-07-13 — after P2.1

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — P2.2 (`plan.md` §3 Routing: P2.1–P2.4 = opus/high,
Exec = manual; по routing-гейту §9, введённому только что item'ом P2.1, `/task:plan-exec`
обязан отказать — `ROUTING-BLOCKED`, модель выше пина команды)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка SSOT-канона (§6 Статусы): предикат material vs process судит `plan-audit` по нему БЕЗ доступа к чату исполнения; закрытый список из 5 триггеров = конфликтные требования + инварианты (SSOT §9: high+ MANDATORY) |
| Context | continue (/clear) — ручной item; items P2 делят один файл `SKILL.ru.md`, строго последовательно (Workflow не заводится) |
| Суть | §6 `SKILL.ru.md`: блок «Статус при отклонениях» (D9/A5 — 🟢 при process, 🟠 при material) + блок «фазовая когерентность» (D17) |

````
Запусти вручную под opus/high (НЕ /task:plan-exec — Exec=manual): исполни item P2.2 плана
2026.07.13-PLAN-PROTOCOL-GAP по протоколу plan-exec (packages/skiller/skills/general/
plan-protocol/SKILL.ru.md §8–11) — прочитай plan.md (Context, Execution Rules, §3 Routing,
D-лог: D9 + новые D15/D16/D17), phases/P2.md (Phase Context + item P2.2 целиком, включая
Completion Notes закрытого P2.1), закрой item по каноническому порядку закрытия §8 (дифф →
validate → bookkeeping → перезапись handoff → plan-lint --baseline HEAD ПОСЛЕ handoff →
коммит). Сверх ТЗ P2.2: в §6 дописывается ТАКЖЕ правило «фазовая когерентность» (D17) —
item фазы вправе оставить производный артефакт (EN-канон SKILL.md) протухшим, если фаза
несёт терминальный item регенерации и он назван в Pending Work; полный зелёный validate.sh
требуется на терминальном item'е фазы.
````

**Done:** P1 терминальна (`4c03715`, `b45cd51`). P2.1 🟢 — `SKILL.ru.md` §9 получил четыре блока:
(1) канон-форма строки `## 3. Routing` — таблица `Items | Model/effort | Exec | Почему`, Exec —
закрытый enum `plan-exec` | `manual` | `plan-design`; (2) тир-порядок — модели
`haiku < sonnet < opus ≈ fable`, effort `low < medium < high < xhigh < max`, пин команды
`plan-exec` = sonnet/medium; (3) деривация Exec (перебор тира безвреден, недобор запрещён — обе
оси) + консистентность заполненной колонки (`Exec = plan-exec` вопреки model/effort = дефект
плана, не разрешение); (4) routing-гейт из 5 веток с двумя кодами отказа — `ROUTING-BLOCKED`
(Exec = manual, задан или выведен) и `ROUTING-INCONSISTENT` (противоречие внутри строки Routing)
+ back-compat-оговорка (легаси-формы §3 валидны, `plan-lint` §3 не парсит — D7). Ревью свежим
контекстом дало 2 Major, оба закрыты ДО коммита (D15: `model ≠ sonnet → manual` давал ложный
СТОП на живых `haiku/low`-items; D16: заполненная Exec перебивала деривацию без правила
консистентности → воспроизводила F7). Полные детали — `phases/P2.md` P2.1 Completion Notes.

**Remaining:** P2.2 (§6 status-rule + фазовая когерентность) → P2.3 (§4/§11 Contracts + парсер
и cross-plan сверка в `plan_lint.py` — правило двух SSOT, оба места в одном item'е) → P2.4
(терминальный: snippets + version 2.3.0 + **регенерация EN-канона** + `skiller registry`) → P3
(4 items, sonnet/medium, команды `plan-*`: гейты и порядок закрытия) → P4 (3 items — регресс по
9 корням флота, закрытие эскалации REGHUB в чужом репо, доки/CHANGELOG).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, Execution Rules, §3
Routing, D-лог D1–D17) · `phases/P2.md` (P2.1 Completion Notes; ТЗ P2.2–P2.4) ·
`findings/P0-protocol-gap-recon.md` · SSOT-цели:
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` (§6 — предмет P2.2, §9 — закрыт),
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- Фаза P2 — правка SSOT-канона: формулировки = public contract для 26 живых планов флота.
  Ошибка тиражируется на весь флот при следующей `plan-design`/`plan-exec` сессии любого плана.
  Ревью P2.1 подтвердило риск эмпирически: обе Major-находки — дефекты САМИХ формулировок ТЗ,
  прошедших дизайн-фазу. Ручной запуск под opus/high + ревью свежим контекстом на items P2 —
  не формальность.
- Routing-гейт §9 уже в SSOT, но в тексте команды `/task:plan-exec` его ещё НЕТ (P3.1): до P3
  гейт исполняется только читающим человеком/агентом, автоматически команда его не применит.
- EN-канон `SKILL.md` протух намеренно (D17) и останется таким до P2.4 →
  `packages/skiller/scripts/validate.sh` красный на `check-translations` всю фазу. Любой
  посторонний прогон validate.sh в этот период даст ERROR — это ожидаемо, а не регресс.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный, вне этого репо.
- Внутри `plans/archive/` (vaulter: VLT-CANON/VLT-REMED несут ERROR/WARNING, впервые
  пролинтованы P1.1) — вне Scope, архивные планы не переоткрываем.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: регенерация EN-канона (P2.4, D17); миграция §3 Routing 26 живых планов на канон-форму
  с колонкой Exec (back-compat: легаси-формы валидны, новую эмитит `plan-design`); кросс-репо
  push-уведомление о bump'е контракта (роадмап, вне scope).
- open_questions: развилки `plan.md` §Обсуждение (авто-делегация в Workflow, релакс ERROR→WARNING
  на скелетах) — отклонены D-логом; возражение владельца перебивает новым D# со `supersedes`.
