# HANDOFF — 2026-07-14 — after P3.2

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high»

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правила остановки аудита (D44), НОВАЯ семантика, не копипаст канона |
| Context | continue (/clear) — ручной item |
| Суть | `plan-audit.md`: правила остановки (scope-граница, потолок раундов, follow-up вместо реопена) + чеклист под канон 2.5.0 (status-rule, якорь дерева, Contracts, RAG-enum) |

```
Это ИСПОЛНЕНИЕ item'а мастер-плана (plan-протокол), item Pn.m = P3.3, план
2026.07.13-PLAN-PROTOCOL-GAP. Routing (§3 plan.md) предписывает opus/high,
Exec = manual — команда `/task:plan-exec` пинит sonnet/medium и обязана
отклонить этот item, поэтому запускаешься под текущей моделью/effort сессии
(владелец уже выставил opus/high).

Прочитай СТРОГО в этом порядке (без повторов, без чтения сверх списка):
1) plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md — Context, §2 Execution Rules,
   §3 Routing, §4 Status Board, §5 Decision Log (особенно D44, D9, D10, D22,
   D23, D26, D27, D29, D34, D36, D38);
2) plans/2026.07.13-PLAN-PROTOCOL-GAP/handoff.md (этот файл) — где мы;
3) plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P3.md — Phase Context целиком +
   item P3.3 целиком (Intent/Why/Scope Included/Scope Excluded/Inputs/Files/
   Required Reads/Implementation Rules/Code Guidance/Validation/Deliverables);
4) файлы из Required Reads item'а P3.3, в указанном там порядке (включая
   roadmap/plan-audit-loop.md и три блока `## Audit P2` в phases/P2.md).

Исполни item P3.3 по протоколу plan-exec (packages/task/commands/plan-exec.md,
раздел "ЗАКРЫТИЕ ОБЯЗАТЕЛЬНО", топология ДВУХ коммитов): пометь Status
🟡 In progress → правь СТРОГО packages/task/commands/plan-audit.md по Scope
Included item'а → Validation item'а → закрытие (item-коммит по Files → book-
keeping → перезапись handoff.md → plan-lint --baseline HEAD ПОСЛЕ handoff →
счёт с атрибуцией → bookkeeping-коммит). Фактическая модель/effort сессии —
ОБЯЗАНА быть напечатана в отчёте и Update Log (граница честности D18/D43,
самоатрибуция машинно не проверяема). Недобор модели/effort против Routing
(opus/high) → СТОП «ROUTING-BLOCKED: P3.3 — предписано opus/high, сессия
<фактическое>», статус НЕ трогать.
```

**Done:** P1, P2 терминальны (P2 — 🟠 Done with deviations, 18/18 items,
скилл `plan-protocol` 2.5.0). **P3 (2/6):** P3.1 закрыт (`4cfc10a`) —
`plan-exec.md` получил routing-гейт, топологию двух коммитов, коммит-гигиену,
status-rule, якорь дерева (124 → 180 строк). **P3.2 закрыт** (item-коммит
`0823cb4`, bookkeeping — этот): `plan-close.md` **113 → 145 строк** (на
`0823cb4`) — enum 8 форм `Next` с правилом D40 (форма — первая непустая
строка поля), две формы заголовка handoff (`after Pn.m` / `after Pn`, D30),
`Context` — enum трёх значений (запрещённое «fresh session» вычищено),
снятие маркера `> УСТАРЕЛ — фаза реопенена <D#>` при закрытии фазы (§3 шаг 4:
снимает ТОЛЬКО `plan-close`), `Last Updated` (D38), `plan-lint --baseline
HEAD` ПОСЛЕ перезаписи handoff со счётом `N ERROR / M WARN — новых от
закрытия: K` (D5/D6). Формулировки сверены дословно с `plan-exec.md`
(diff словами — расхождений не найдено).

**Remaining:**

1. **P3** (2/6): **P3.3 `plan-audit` ← Next (ЗАПУСК ВРУЧНУЮ, opus/high)** →
   P3.4 `plan-design` → P3.5 `plan-run` → **P3.6 терминальный** (ЗАПУСК
   ВРУЧНУЮ, opus/high — §13 SSOT + EN-канон 2.6.0 + сквозная сверка).
   Порядок обязателен: P3.4/P3.5 читают тело `plan-exec.md` ПОСЛЕ P3.1
   (уже готово); P3.3 не зависит от них.
2. P4 (3 items): регресс по флоту (P4.1), закрытие эскалации REGHUB (P4.2,
   чужой репо Brain), доки + CHANGELOG (P4.3).
3. Аудит фазы P3 — по НОВЫМ правилам остановки (после P3.3 — циклическая
   зависимость: P3.3 сама вводит эти правила в текст `plan-audit.md`, аудит
   P3 их читает уже готовыми): один заход, RED только на сломанном продукте,
   бухгалтерия → ATTENTION + Pending Work, реопена по умолчанию нет.

**Sources of truth:** `plan.md` (Meta **1.4.0**, §2 Execution Rules + carve-out
D34, §3 Routing — **P3.1/P3.3/P3.6 = opus/manual**, §5 D-лог **D1–D45**,
`## Обсуждение` — 9 развилок со статусами) · `phases/P3.md` (**6 items**,
P3.1/P3.2 🟢) · `phases/P4.md` (скелет) · `findings/P0-protocol-gap-recon.md`,
`findings/P2-third-reopen-fleet-measurements.md`, `findings/P3-command-layer.md`
(матрица дыр §2, потолки объёма §3) · SSOT канона:
`packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник
2.5.0; `SKILL.md` — EN-канон; `snippets/`) · `packages/task/lib/task/plan_lint.py`
· `packages/task/commands/plan-exec.md` (эталон формулировок, 180 строк,
на потолке) · **`packages/task/commands/plan-close.md` — правлен, эталон
для будущих сверок enum'ов Next/Context**.

**Open risks:**
- **Тело `plan-exec.md` на потолке — 180/180 строк.** P3.5 обязан дописать в
  его launch-block строку-альтернативу `/task:plan-run` ⇒ сперва высвободить
  строки сокращением ПРОЗЫ либо согласовать поднятие потолка
  (`findings/P3-command-layer.md` §3). **`plan-close.md` теперь тоже на
  потолке — 145/145 строк** (тот же риск для P3.3/P3.4, если понадобится
  дописать в него строку).
- Канон 2.5.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44):
  механический класс закрыт конфликт-сканом. Первое живое применение — эта
  фаза (P3.1/P3.2 расхождений канона не нашли).
- Три команды `/task:plan-*` (`plan-audit`, `plan-design`, `plan-run` — новая)
  правил канона ещё НЕ несут — до закрытия P3 гейты держатся дисциплиной
  исполнителя.
- Два чужих плана флота несут WARNING по гейту H2 (VLT-REMED/P5,
  2026.07.12-BASE/P5 — themeon): приняты владельцем как истинно-положительные
  (D34/D39); их правка — вне scope.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там
  отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: раскатка директив `i18n-keep` на остальные локальные скиллы;
  миграция §3 Routing / `## Обсуждение` живых планов на канон-форму
  (back-compat); заполнение `## 7. Contracts` в живых планах (REGHUB — P4.2);
  правка `## Phase Handoff` двух чужих планов (вне scope); кросс-репо
  push-уведомление (роадмап); CHANGELOG + docs пакетов (P4.3);
  **[POSSIBLE-DEFECT]** нестабильный порядок вывода диагностик `plan-lint`
  между прогонами (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: все девять развилок `plan.md` `## Обсуждение` несут
  `**Статус:** Resolved → D#` → незакрытых нет, `open-questions.md` плану
  не заводится (правило §3).
</content>
