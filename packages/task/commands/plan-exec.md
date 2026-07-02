---
description: "План-протокол: исполнить подпункт(ы) Pn.m мастер-плана из plans/ строго по ТЗ, с обязательным закрытием item'а и handoff. Пинит Sonnet/medium."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
model: sonnet
effort: medium
---
Это ИСПОЛНЕНИЕ item'а мастер-плана (plan-протокол). Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Sonnet/medium) — не переключай вручную. Команда самодостаточна:
весь протокол ниже, скилл `plan-protocol` дочитывай только при явной ссылке из плана.
Несколько item'ов в аргументах — исполняй последовательно, каждый по полному циклу 1–8.

1. **Порядок чтения — РОВНО такой, ничего сверх:**
   1) `plans/<PLAN-ID>/plan.md` — Context, Execution Rules, Routing, Status Board;
   2) `plans/<PLAN-ID>/handoff.md` — где мы;
   3) `plans/<PLAN-ID>/phases/Pn.md` — Phase Context + твой item Pn.m целиком;
   4) файлы из **Required Reads** item'а — в указанном порядке.
   Повторное чтение уже прочитанного ЗАПРЕЩЕНО (экономия контекста); «почитаю ещё по
   репо на всякий случай» — тоже. Всё нужное обязан нести план; не несёт — см. п. 5.

2. **Предусловия.** Статус item'а — `⬜ Not started` или `🟡 In progress`; иначе стоп и отчёт
   (терминальный item не переисполняется). **Phase-first:** item фазы N+1 не исполняется,
   пока фаза N не терминальна (все её items 🟢/🟠/⛔) — иначе стоп + отчёт, какая фаза держит.

3. **До работы:** пометь `**Status:** 🟡 In progress` у item'а И строку в таблице
   `## Phase Status` (статусы — 6 канонических строк байт-в-байт, копируй из плана).

4. **Исполнение — СТРОГО в Scope Included.** Implementation Rules и Code Guidance item'а —
   жёсткие рамки, не рекомендации. Заметил «улучшить бы заодно» — запиши в **Pending Work**
   item'а, НЕ делай. План разошёлся с реальным кодом (файла нет, сигнатура другая, якорь
   не находится) → НЕ импровизировать, НЕ «чинить план на ходу» → эскалация (п. 5):
   план правит plan-design, а не исполнитель.

5. **Эскалация.** Триггеры (закрытый enum): многопакетный рефакторинг · неясная архитектура ·
   public contract/SemVer · protected generated assets · конфликт правил · неясные acceptance.
   При срабатывании оставь ТРИ greppable-артефакта и остановись:
   - blockquote в item: `> 🔴 ESCALATION Pn.m: <причина> | trigger: <из enum> | нужен: plan-design`;
   - `**Status:** 🔴 Blocked` у item'а (и в Phase Status) + `**Escalation Needed:** yes`;
   - обнови `handoff.md` (Next: /task:plan-design <PLAN-ID> Pn.m; причина — в Open risks);
   - финальная строка отчёта: `ESCALATION-REQUIRED: Pn.m — <причина>`.

6. **Validation.** Прогони КАЖДУЮ команду из поля **Validation** item'а; зафиксируй результат
   (команда → passed/failed + суть вывода). Красное — чини в рамках Scope; не чинится в рамках —
   это `🟠 Done with deviations` с Known Deviations либо эскалация, НЕ молчаливый пропуск.

7. **ЗАКРЫТИЕ ОБЯЗАТЕЛЬНО** — без него работа НЕ выполнена, даже если код написан:
   - `**Status:**` → `🟢 Done` (или `🟠 Done with deviations` + заполненные **Known Deviations**);
   - **Completion Notes** — только факты: изменённые файлы, добавленные тесты,
     прогнанные команды и их вывод (без оценок «всё отлично»);
   - **Pending Work** — накопленное из п. 4 (или «—»);
   - синхронизируй строку в `## Phase Status` фазы И `## 4. Phase Index & Status Board`
     в `plan.md` (счётчик `Items 🟢/всего`, статус фазы);
   - ПЕРЕЗАПИШИ `plans/<PLAN-ID>/handoff.md` целиком по схеме:
     `# HANDOFF — <ISO-дата> — after Pn.m`, затем строки **Next:** (конкретная команда
     `/task:plan-exec <PLAN-ID> Pn.k`) / **Done:** / **Remaining:** / **Sources of truth:** /
     **Open risks:** / **Workarounds/Deferred/Open questions:** (три подпункта:
     workarounds · deferred · open_questions; «—» если нет);
   - прогони `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<PLAN-ID>`
     (переменная не задана или скрипта нет — предупреди и пропусти); красное почини.

8. **Expected output — фиксированный формат (по блоку на item):**
   ```
   ### Pn.m — <Title>
   Status: 🟢 Done | 🟠 Done with deviations | 🔴 Blocked
   Completed: <что сделано, 1–3 строки>
   Pending Work: <…|—>
   Files Changed: <список путей>
   Validation: passed|failed — <команды и суть>
   Known Deviations: <…|—>
   Escalation Needed: no|yes (тогда финальная строка ESCALATION-REQUIRED: …)
   Next Suggested Step: execute plan Pn.k
   Context: handoff свежий — рекомендован /clear перед следующим item
   ```
