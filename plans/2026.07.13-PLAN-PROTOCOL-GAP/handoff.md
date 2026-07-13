# HANDOFF — 2026-07-13 — after P2.5

**Next:** ЗАПУСК ВРУЧНУЮ — P2.6 (§3/§4 носитель развилок: секция Обсуждение + трекер)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка SSOT-канона протокола (§3 Routing: `P2.5–P2.6 \| opus/high \| manual`) |
| Context | NEW SESSION — правки канона идут в один файл; исполнителю нужен свежий контекст |
| Суть | Канонизировать носитель развилок (D23): в §4 — опциональная ненумерованная секция `## Обсуждение` с ОБЯЗАТЕЛЬНОЙ строкой статуса у каждой развилки; в §3 — разграничение с `open-questions.md` (план = провенанс, файл = трекер незакрытого); + образец в `snippets/plan-template.md` и уточнение DoR-чеклиста §7 |

````
Исполни item P2.6 плана 2026.07.13-PLAN-PROTOCOL-GAP (репо swissknifeman) строго по ТЗ.

ТЗ: plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md, раздел «### P2.6 — §3/§4 носитель
развилок: секция Обсуждение + трекер (F3)» — все 16 полей, включая Code Guidance и Validation.
Правила плана: plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md §2 Execution Rules, §5 D23 (+D20 —
прецедент back-compat: секция опознаётся без привязки к номеру).
Основание: находка F3 в блоке «## Audit P2 — 2026-07-13» (конец phases/P2.md).

Правятся ДВА файла: packages/skiller/skills/general/plan-protocol/SKILL.ru.md (§3/§4/§7) и
.../plan-protocol/snippets/plan-template.md. EN-канон SKILL.md руками НЕ править —
регенерация в терминальном item'е фазы P2.8 (правило фазовой когерентности §6/D17): красный
check-translations внутри фазы легален, но обязан быть НАЗВАН в Pending Work и в отчёте.

Закрытие item'а — по канону §8: дифф → validate.sh → bookkeeping плана (Phase Status,
Status Board, Update Log) → перезапись handoff.md → `python3 packages/task/scripts/plan-lint.py
plans/2026.07.13-PLAN-PROTOCOL-GAP --baseline HEAD` ПОСЛЕ handoff → счёт с атрибуцией
(«новых от диффа item'а: K», гейт K=0) → коммит ПО ЯВНЫМ ПУТЯМ (`git add <Files> <файлы
плана>`; `git add -A` запрещён — §6 канона, правило введено P2.5).
````

**Done:** P1 терминальна (`4c03715`, `b45cd51`). Фаза P2 — **5/8**: `38954ab` P2.1 §9
routing-гейт · `cd749ab` P2.2 §6 status-rule · `1451ed9` P2.3 §4/§11 Contracts + линтер ·
`365079c` P2.4 snippets + EN-канон 2.3.0 (закрыт 🟢, но аудит нашёл F1/F2 → статус переоценят
в P2.7) · `c90b5fb` реопен P2 по RED-аудиту (plan-design, D21–D25) · **`4a4af60` P2.5 — §6
коммит-гигиена + 6-й material-триггер (D22)**.

Что даёт P2.5 в SSOT: item-коммит собирается ПО ЯВНЫМ ПУТЯМ (`git add <Files> <файлы плана>`),
`git add -A` / `git commit -a` ЗАПРЕЩЕНЫ; посторонний дифф рабочего дерева исполнитель НЕ
трогает (не коммитит, не стэшит, не ревертит) — НАЗЫВАЕТ в отчёте. Предикат material в §6 стал
закрытым списком из **6** триггеров (новый: «item-коммит несёт дифф вне `Files` item'а —
независимо от того, верен ли сам дифф»). Правило применено к самому себе с первого прогона:
некоммиченный дифф plan-design ушёл отдельным коммитом `c90b5fb` ДО item-коммита.

**Remaining:** P2.6 (§3/§4 носитель развилок, opus/manual — СЛЕДУЮЩИЙ) → P2.7 (ремедиация
плана: P2.4 → 🟠, статусы развилок, F4 — sonnet, `/task:plan-exec`) → P2.8 (терминальный:
version 2.4.0 + регенерация EN-канона + registry, opus/manual) → повторный аудит P2 → P3
(5 items) → P4 (3 items).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D25, `## Обсуждение`) · `phases/P2.md` (ТЗ P2.6–P2.8 + Completion Notes
P2.1–P2.5 + блок `## Audit P2`) · `phases/P3.md`, `phases/P4.md` (ТЗ следующих фаз; в них уже
вписаны зеркала D22/D23) · SSOT канона: `packages/skiller/skills/general/plan-protocol/`
(`SKILL.ru.md` 2.3.0 — источник; `SKILL.md` — EN-канон, генерируется; `snippets/`) ·
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- **EN-канон протух** (`check-translations` красный в `packages/skiller/scripts/validate.sh`):
  P2.5 и P2.6 правят RU-источник, регенерация — в терминальном P2.8. Легально по §6/D17 ТОЛЬКО
  потому, что терминальный item в фазе есть и назван; молча закрыть фазу с протухшим EN = ложь
  в Completion Notes. До P2.8 правила P2.5/P2.6 агентам флота НЕ доехали (RU в контекст не грузится).
- **Правила уже в SSOT, но команды `/task:plan-*` их ещё не исполняют** (фаза P3): routing-гейт,
  status-rule и коммит-гигиену применяет только читающий человек/агент. F1 — прямое следствие
  этого разрыва: канон запрещал коммитить чужой дифф, а команда `plan-exec` про это молчит.
  Зеркало D22 в `plan-exec`/`plan-close`/`plan-audit` — P3.1/P3.2/P3.3.
- P2.6 расширяет схему §4 новой секцией — риск back-compat: у живых планов (`vaulter/VLT-HSEAM`,
  `themeon`) секция `## Обсуждение` уже есть, но БЕЗ статусов. Поэтому линтер её НЕ парсит (D23,
  прецедент D20) — гейт только в DoR-чеклисте §7 и в `plan-audit`.
- Статус P2.4 остаётся 🟢 до P2.7 (по 6-му триггеру §6 обязан стать 🟠) — доска до этого момента
  завышена на один item.
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
