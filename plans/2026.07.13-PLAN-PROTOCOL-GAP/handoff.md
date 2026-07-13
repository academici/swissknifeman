# HANDOFF — 2026-07-13 — after P2.4

**Next:** /task:plan-audit 2026.07.13-PLAN-PROTOCOL-GAP P2

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | xhigh — adversarial-аудит закрытой фазы (пин команды `plan-audit`) |
| Context | NEW SESSION — аудит требует свежего контекста (исполнитель фазы не аудитор самого себя) |
| Суть | Аудит терминальной фазы P2 (4/4 🟢): сверка канона с git-фактами, no-op, scope drift, качество handoff; в items есть Known Deviations process-класса (D17/D19/D20) — проверить по новому status-rule §6 |

````
/task:plan-audit 2026.07.13-PLAN-PROTOCOL-GAP P2
````

**Done:** P1 терминальна (`4c03715`, `b45cd51`). **Фаза P2 терминальна — 4/4 🟢**:
- P2.1 (`38954ab`) — §9: канон-форма строки `## 3. Routing` (колонка `Exec` = `plan-exec` |
  `manual` | `plan-design`), тир-порядок (`haiku < sonnet < opus ≈ fable`; `low < medium < high
  < xhigh < max`), деривация Exec + консистентность заполненной колонки, routing-гейт из 5 веток
  (`ROUTING-BLOCKED` / `ROUTING-INCONSISTENT`), back-compat легаси-форм (F7).
- P2.2 (`cd749ab`) — §6: status-rule (5 material-триггеров → 🟠; process → 🟢 + обязательная
  запись; недобор модели/effort вынесен из предиката — запрещён гейтом §9), «фазовая
  когерентность производного» (D17), «дефект ТЗ ≠ отклонение исполнителя» (D19).
- P2.3 (`1451ed9`) — §4/§11 + `plan_lint.py` синхронно (правило двух SSOT): опциональная секция
  `## 7. Contracts`, cross-plan notification, парсер + root-сверка `Consumed.Pinned` ↔
  `Exported.Версия` → WARNING; тесты 104 → 109 (m7).
- P2.4 — snippets (Routing-форма, enum `Next`, «ЗАПУСК ВРУЧНУЮ»), `version: 2.3.0`, **регенерация
  EN-канона** (493 → 620 строк при гейте ≤620; EN отставал ещё с P1.1), `--stamp`, `skiller
  registry`. `packages/skiller/scripts/validate.sh` — **зелёный** (D17 погашен на терминальном
  item'е фазы, ровно как предписывает правило фазовой когерентности).

Между фазами владелец принял **D18** (`fc57561`) → новый item **P3.5**: команда `/task:plan-run`
БЕЗ пина модели (наследует модель/effort сессии), чтобы manual-items не требовали ритуала
`/model` + `/effort` + вставки промпта; жёсткий гейт остаётся за `plan-exec`.

Гейт back-compat выдержан: регресс по 9 корням флота — **0 новых ERROR, 0 новых WARNING**; он же
поймал дефект ТЗ P2.3 → D20 (секция Contracts опознаётся по заголовку, а не по номеру 7).

**Remaining:** аудит P2 → P3 (5 items, sonnet/medium: routing-гейт в `plan-exec`, честный lint
закрытия в `plan-close`, чеклист `plan-audit`, эмит канон-формы в `plan-design`, новая команда
`plan-run`) → P4 (3 items: регресс по флоту, закрытие эскалации REGHUB в чужом репо,
доки/CHANGELOG).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, Execution Rules, §3
Routing, D-лог D1–D20) · `phases/P2.md` (Completion Notes P2.1–P2.4 + Phase Handoff) ·
`phases/P3.md` (ТЗ P3.1–P3.5) · SSOT: `packages/skiller/skills/general/plan-protocol/`
(`SKILL.ru.md` 2.3.0 — источник; `SKILL.md` — EN-канон, регенерирован; `snippets/`) ·
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- Правила уже в SSOT (их читает КАЖДЫЙ агент флота — скилл в CORE), но команды `/task:plan-*`
  их ещё не исполняют: до P3 routing-гейт и status-rule применяет только читающий человек/агент.
  Разрыв «канон есть — исполнителя нет» — самая опасная точка плана прямо сейчас.
- Items фазы P2 несут Known Deviations process-класса (D17 — красный validate.sh внутри фазы;
  D19/D20 — правки ТЗ по новым D#). Все три легальны по status-rule §6, но аудит обязан их
  проверить ИМЕННО по предикату, а не «на глаз» — это первый прогон нового правила на живой фазе.
- `check-translations.sh --stamp` дописывает второй маркер `ru-source-sha256` вместо замены
  плейсхолдера `PENDING` (промт генерации предписывает `PENDING`) — обошли вручную; дефект
  скрипта skiller, вне scope плана.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: удаление строки-заглушки `<!-- ru-source-sha256: PENDING -->` вручную после
  `--stamp` (обходка в процессе, не в артефакте — файл корректен).
- deferred: фикс `check-translations.sh --stamp` (skiller, отдельный item); миграция §3 Routing
  26 живых планов на канон-форму с колонкой Exec (back-compat: легаси валидны); заполнение
  секции `## 7. Contracts` в живых планах (REGHUB — P4.2); кросс-репо push-уведомление о bump'е
  контракта (роадмап).
- open_questions: развилки `plan.md` §Обсуждение (авто-делегация в Workflow, релакс ERROR→WARNING
  на скелетах) — отклонены D-логом; возражение владельца перебивает новым D# со `supersedes`.
