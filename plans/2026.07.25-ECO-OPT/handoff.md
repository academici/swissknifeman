# HANDOFF — 2026-07-28 — after P4

**Фаза P4 закрыта `🟠 Done with deviations`** (все три item'а терминальны — P4.1 🟢/P4.2 🟠/P4.3 🟠):
вариант 1 роадмап-стаба (единственный демон-хост + сетевые клиенты) реализован — `ADR-0001` фиксирует
восемь принятых решений (D78/D80), `memory.role` (standalone/host/client) с запретом второго писателя
кодом, bearer-аутентификация через аддитивный `core.http`, различение 401/недоступен, измеренный
бюджет ожидания, LAN-bind `iii-config.yaml`, роль-осознанная ступень 5 `bootstrap-machine.sh`. Из
шести приёмочных гейтов rollout'а прогнан и зелён только гейт 3 (`Linger=yes`); гейты 1/2/4 не
прогнаны (нет второй физической машины), гейт 5 не завершён (находка F1 — mesh-discovery движка),
гейт 6 не прогнан (находка F2 — `doctor.py` не роль-осознан) — материальное отклонение Scope
Included, `🟠` предписан status-rule. Docs-sync: обновлено (`memory.md`, `deploy.md`, `systemd.md`,
`CHANGELOG.md` — уже в item-коммитах). Гейты закрытия фазы: `maind test.sh` — 534 tests, 2
пред-существующих FAIL (P3.2/P5.3, не регрессия); `core.tests` — зелёный; `plan-lint --baseline
HEAD` — 0 ERROR, 27 WARN, новых от закрытия: 0. `closure/P4.json` создан. Детали — `phases/P4.md`
Phase Handoff / Completion Notes всех трёх item'ов.

**Next:** **`/task:plan-exec 2026.07.25-ECO-OPT P6.2`** — фаза P4 терминальна, следующий шаг по
roadmap (`roadmap.md` §B3, батч «контекст-гигиена») — P6.2, `Exec=plan-exec`,
`implementation/medium`; P6.1/P6.3 идут отдельными `manual`-сессиями той же фазы (не батчем).

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — предписано роадмапом (P6.2, implementation/medium) |
| Context | continue (/clear) — ручной item |
| Суть | P6.2: compact-дисциплина в двух скиллах (батч B3) |

```
/task:plan-exec 2026.07.25-ECO-OPT P6.2
```

**Done:** **44/52 items терминальны** (28 🟢 · 15 🟠 · 1 ⛔). Закрыты фазы **P1** (1/2, 🟢), **P4**
(1/3, 🟠 — только что закрыта), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9** (3/4, 🟠), **P10** (1/4,
🟠), **P11** (6/8, 🟠); частично — **P3** (2/6, 🟠). Вне этих фаз закрыт только P2.1.

**Remaining:** 8 items, все `⬜ Not started`: P2.2/P2.3 · P6.1–P6.3 · P7.1–P7.3. Порядковые условия:
P2.3 — ПОСЛЕ P6.3 (D93) и ПОСЛЕ P8.1/P8.2/P8.3 (терминальны); P6.1 — ПОСЛЕ P9.1 (снято, терминален);
P7.1 + P7.3 → P7.2.

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index — `P4 1/3` со статусом
`🟠 Done with deviations`; §6 Update Log — запись закрытия фазы P4) · `phases/P4.md` (Phase Status +
Phase Handoff) · `closure/P4.json` · `findings/P4.3-rollout-report.md` · `docs/deploy.md` (раздел
«Вторая машина») · `packages/maind/docs/guide/systemd.md` (linger) · машинные гейты
`packages/task/scripts/plan-lint.py`, `plans/verify-citations.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей) плюс:
(40) **Находка F1 (mesh-discovery, `findings/P4.3-rollout-report.md`)**: любой новый локальный
процесс `agentmemory` на этой машине автоматически присоединяется к mesh-группе живого демона —
угрожает инварианту «один писатель» при любом будущем локальном эксперименте с памятью; нет
митигации на уровне кода, только процессная осторожность.
(41) **Находка F2 (`doctor.py:246-253` не роль-осознан)**: на реальном клиенте `maind doctor`
покажет ложные `FAIL` по отсутствующим локальному Node/agentmemory — вне Scope P4, кандидат в новый
item/roadmap.
(42) **Гейты 1/2/4/5/6 P4.3 не подтверждены** — требуют физической второй машины; выполнить и
дополнить `findings/P4.3-rollout-report.md`, когда машина появится (фаза P4 терминальна по правилу
«🟠 при material-отклонении», не «ждать снятия Pending Work»).

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — roadmap-кандидат **F1** (дисциплина против класса R2, P3.3) не внесён в
`roadmap.md`; расхождение 142 vs 186 записей `flexcrm` (P3.1) не разобрано до корня;
`oss-dev/to-issues/upstream.json` — апстрим-URL вернул 404, паспорт нуждается в обновлении; протокол
проверки backup-restore (ADR-0001 п.7) нуждается в пересмотре метода (находка F1 показывает, что
«изолированная копия» на одной машине технически не изолирована от mesh-discovery движка) —
кандидат в roadmap/новый D#, не решён этой фазой.
· **open questions** — нет новых этим заходом; OQ-11 остаётся `Decision pending` до закрытия P11.
