# HANDOFF — 2026-07-13 — after P2.4

**Next:** ЗАПУСК ВРУЧНУЮ — P2.5 (§6 коммит-гигиена + 6-й material-триггер)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка SSOT-канона протокола (§3 Routing: `P2.5–P2.6 \| opus/high \| manual`) |
| Context | NEW SESSION — фаза реопенута по RED-аудиту; исполнителю нужен свежий контекст |
| Суть | Закрыть дыру, через которую прошёл F1: §6 требует «не коммитить чужой дифф», но без операционной формы (`git add` по путям) и без последствия для статуса → `git add -A` в P2.4 захватил рабочее дерево владельца, а item закрылся 🟢 |

````
Исполни item P2.5 плана 2026.07.13-PLAN-PROTOCOL-GAP (репо swissknifeman) строго по ТЗ.

ТЗ: plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md, раздел «### P2.5 — §6 коммит-гигиена
item'а + 6-й material-триггер (F1/F2)» — все 16 полей, включая Code Guidance и Validation.
Правила плана: plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md §2 Execution Rules, §5 D21/D22.
Основание: блок «## Audit P2 — 2026-07-13» в конце phases/P2.md (находки F1/F2).

Правится ОДИН файл: packages/skiller/skills/general/plan-protocol/SKILL.ru.md (§6).
EN-канон SKILL.md руками НЕ править — регенерация в терминальном item'е фазы P2.8
(правило фазовой когерентности §6/D17): красный check-translations внутри фазы легален,
но обязан быть НАЗВАН в Pending Work и в отчёте.

Закрытие item'а — по канону §8: дифф → validate.sh → bookkeeping плана (Phase Status,
Status Board, Update Log) → перезапись handoff.md → `python3 packages/task/scripts/plan-lint.py
plans/2026.07.13-PLAN-PROTOCOL-GAP --baseline HEAD` ПОСЛЕ handoff → счёт с атрибуцией
(«новых от диффа item'а: K», гейт K=0) → коммит ПО ЯВНЫМ ПУТЯМ (`git add <Files> <файлы
плана>`; `git add -A` запрещён — это ровно то правило, которое ты вводишь этим item'ом).
````

**Done:** P1 терминальна (`4c03715`, `b45cd51`). Фаза P2 — 4 items закрыты (`38954ab` P2.1 §9
routing-гейт · `cd749ab` P2.2 §6 status-rule · `1451ed9` P2.3 §4/§11 Contracts + линтер ·
`365079c` P2.4 snippets + EN-канон 2.3.0), но **фаза РЕОПЕНУТА по вердикту аудита** (D24):

- **Аудит P2 → 🔴 RED** (2 Major): F1 — коммит P2.4 сделан `git add -A` и захватил чужой дифф
  (`packages/skiller/lib/skiller/integrate.py`, дефолт auto-approve `strict` → `bypass`);
  F2 — при этом item закрыт 🟢, хотя §6 (правило, введённое ЭТОЙ ЖЕ фазой) требует 🟠.
  Полный блок находок — `phases/P2.md`, `## Audit P2 — 2026-07-13`.
- **Решения владельца (2026-07-13):** D21 — bypass-правка признана его намеренным решением
  (часть кластера, продолженного `e23f10d`/`2456b66`): код НЕ откатываем, коммит не
  переписываем, провенанс восстанавливаем (D# + Update Log + CHANGELOG в P4.3). D22 —
  коммит-гигиена + 6-й material-триггер в §6. D23 — носитель развилок (`## Обсуждение` в
  схеме + `open-questions.md` как трекер незакрытого). D25 — скилл 2.3.0 → 2.4.0.
- Version плана 1.0.0 → **1.1.0**; Status Board P2 → **4/8 🟡**.

**Remaining:** P2.5 (§6 коммит-гигиена, opus/manual) → P2.6 (§3/§4 носитель развилок,
opus/manual) → P2.7 (ремедиация плана: P2.4 → 🟠, статусы развилок, F4 — sonnet,
`/task:plan-exec`) → P2.8 (терминальный: version 2.4.0 + регенерация EN-канона + registry,
opus/manual) → повторный аудит P2 → P3 (5 items) → P4 (3 items).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D25, `## Обсуждение`) · `phases/P2.md` (ТЗ P2.5–P2.8 + Completion Notes
P2.1–P2.4 + блок `## Audit P2`) · `phases/P3.md`, `phases/P4.md` (ТЗ следующих фаз; в них уже
вписаны зеркала D22/D23) · SSOT канона: `packages/skiller/skills/general/plan-protocol/`
(`SKILL.ru.md` 2.3.0 — источник; `SKILL.md` — EN-канон, генерируется; `snippets/`) ·
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- **Правила уже в SSOT, но команды `/task:plan-*` их ещё не исполняют** (фаза P3): пока routing-гейт,
  status-rule и коммит-гигиену применяет только читающий человек/агент. F1 — прямое следствие
  этого разрыва: канон запрещал коммитить чужой дифф, а команда `plan-exec` про это молчит.
- P2.5–P2.8 снова правят RU-источник → EN-канон протухает внутри фазы. Легально по §6/D17 ТОЛЬКО
  потому, что фаза несёт терминальный item регенерации (P2.8); молча закрыть фазу с протухшим EN =
  ложь в Completion Notes.
- P2.6 расширяет схему §4 новой секцией — риск back-compat: у живых планов (`vaulter/VLT-HSEAM`,
  `themeon`) секция `## Обсуждение` уже есть, но БЕЗ статусов. Поэтому линтер её НЕ парсит (D23,
  прецедент D20) — гейт только в DoR-чеклисте и в `plan-audit`.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: `check-translations.sh --stamp` ДОПИСЫВАЕТ второй маркер `ru-source-sha256` вместо
  замены плейсхолдера `PENDING` — строку-заглушку удаляем вручную (обходка в процессе, файл
  корректен). Понадобится снова в P2.8.
- deferred: фикс `check-translations.sh --stamp` (дефект skiller, отдельный item вне плана);
  миграция §3 Routing 26 живых планов на канон-форму (back-compat: легаси валидны); заполнение
  `## 7. Contracts` в живых планах (REGHUB — P4.2); кросс-репо push-уведомление о bump'е контракта
  (роадмап).
- open_questions: развилки `plan.md` `## Обсуждение` — все четыре закрыты D-логом (D1/D3 · D5/D6/D11 ·
  D10 · D9); строки статусов проставит P2.7 (D23). Незакрытых развилок нет → `open-questions.md`
  плану не заводится.
