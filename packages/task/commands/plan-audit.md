---
description: "План-протокол: adversarial-аудит закрытой фазы Pn — сверка 🟢 с кодом/git, no-op, scope drift, качество handoff. Пинит Opus/xhigh."
argument-hint: "<PLAN-ID> Pn"
model: opus
effort: xhigh
---
Это ADVERSARIAL-АУДИТ закрытой фазы мастер-плана (plan-протокол). Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Opus/xhigh) — не переключай вручную. Items НЕ трогай, код НЕ меняй.

Профиль `plan-audit`:
1. **Свежим контекстом.** Не доверяй Completion Notes на слово — ты проверяешь исполнителя,
   который сам себе их писал. Суди по git/коду: `git log`/`git diff` по Files каждого item'а
   (slice, не файлы целиком).
2. **Чеклист** (по каждому пункту — вердикт с доказательством):
   - каждая `🟢`/`🟠` сверяется с git/кодом: правки реально существуют и делают заявленное
     (**no-op detection** — статус закрыт, а содержательного диффа нет);
   - диффы ВНЕ полей Files/Scope Included item'ов фазы (**scope drift** — сделано то,
     чего план не просил);
   - дублирующиеся шаги между items (одно и то же «сделано» дважды — признак слепого исполнения);
   - **Validation реально прогнана**: команды из поля Validation воспроизводимы — прогони их
     сам и сверь с заявленным результатом;
   - workarounds из `.claude/runs/*.json` (телеметрия devloop: `devloop{workarounds,deferred,
     open_questions}`) отражены в Pending Work/Known Deviations items — обходка, осевшая
     только в телеметрии, = скрытое отклонение;
   - `handoff.md` и `## Phase Handoff` достаточны для холодного старта: агент без этого чата
     поймёт, где правда и что делать дальше.
3. **Детект ≠ гейтинг.** Репортишь ВСЕ находки: `severity ∈ {LOW,MED,HIGH,CRITICAL}` +
   `file:line` + `failure_scenario` (конкретный сценарий, где это ломает план/код);
   при сомнении ставь ВЫШЕ, сам не отбрасывай.
4. **Единственная разрешённая запись** — append-блок `## Audit Pn — <YYYY-MM-DD>` в КОНЕЦ
   `plans/<PLAN-ID>/phases/Pn.md`: вердикт + findings. Статусы/поля items НЕ править —
   их разруливают plan-design/plan-close по твоему отчёту.
5. Находка, достойная повышения в скилл/правило экосистемы (повторяемый анти-паттерн
   исполнителя, дыра протокола), — пометь `PROMOTE-CANDIDATE` в тексте finding'а.

**Expected output:** вердикт `GREEN` (расхождений нет) / `ATTENTION` (есть MED/LOW) /
`RED` (HIGH/CRITICAL: no-op под 🟢, невоспроизводимая Validation, scope drift с поломкой) +
список findings (severity · item · file:line · failure_scenario).
