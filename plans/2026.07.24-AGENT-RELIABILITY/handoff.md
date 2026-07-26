# HANDOFF — 2026-07-26 — after P4.4

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P4.5

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `medium` |
| Capabilities | — |
| Model | `sonnet` |
| Thinking | `medium` |
| Context | `same-session — item` |
| Суть | Оплатить Contribution gate D23: минорные бампы `analyst 0.1.0 → 0.2.0` и `harness 0.3.0 → 0.4.0`, owed с P3.1; печать кодов границ теперь под машинным гейтом P4.4 |

```
task:plan-exec 2026.07.24-AGENT-RELIABILITY P4.5
```

**Done:**

- **Фаза P4 доведена до DoR** заходом `plan-design … P4` (Claude Opus 5/high). Входной гейт
  «P4 не стартует до GREEN» (D81) **переопределён D89**: принят measured-scope Owner packet;
  план НЕ терминируется на `🟠`. Приёмка объявлена формально НЕ выполненной — floors не
  повышаются, замороженные контракты/банк (владелец P0.3) не правятся, слово GREEN в доках и
  packet'е не появляется. Состав фазы — 5 items (D90, порядок `P4.4 → P4.5 → P4.1 → P4.2 →
  P4.3`); оркестрация объявлена (D93, carrier `workflows/wf-agent-reliability-p4.js`).
- **P4.4 закрыт 🟢** (item-коммит `4ca7af67`): новое правило `plan_lint`
  (`_lint_write_site_codes_44`) — item `🟢`/`🟠`, чей `Updated` (`## Phase Status`)
  ISO-датирован ≥ `2026-07-27`, обязан нести оба кода `pre_mutation:`/`pre_final:` = `allow`
  в Completion Notes; отсутствие любого кода или значение ≠ `allow` — ERROR; вне скоупа —
  молчание (не WARNING). Ремонт `findings/P3.11-terminal-audit-2.md` § Ф2 (reopen F3, событие
  2 из 2): пять items P3.6–P3.10 закрылись без записи кодов, хотя предикат держался. Шесть
  тестов (четыре обязательных различающих кейса D79 + два defensive), T1/T2 канон-литералов
  зелёные, одна строка канона `plan-protocol` §8 в обоих языках → `2.15.0`, публикация
  `skiller@0.8.0`/units `core`/`general@0.8.0`, `registry --check` — «артефакты актуальны»,
  `repository-bootstrap` байт-идентичен. Собственный `Updated` этого item'а (`2026-07-26`)
  намеренно < cutoff `2026-07-27` — self-conformance доказана тестовыми фикстурами, не
  самоприменением; коды границ напечатаны (`pre_mutation: allow`, `pre_final: allow`) потому,
  что предсуществующий канон (P2.7/P2.11) уже требовал их до этого правила. Детали —
  `phases/P4.md` P4.4 Completion Notes.

**Remaining:**

- **Четыре items фазы P4** — P4.5 (следующий, D90), P4.1, P4.2, P4.3 — ни один не стартовал
  (`⬜`). Ручной фолбэк по items описан в `roadmap.md` § «Фаза P4 — carrier оркестрации»; carrier
  `wf-agent-reliability-p4.js` остаётся доступным как альтернативный launch-путь (P4.4 закрыт
  этим заходом маршрутом `task:plan-run`, не carrier'ом).
- **G1** — единственный действующий Owner-гейт: принимается ВЛАДЕЛЬЦЕМ после packet'а P4.3
  (fleet/consumers/FOREMAN/tag/push/release либо hold). Ни один агент прогона наружу не выходит.
- **Строка доски P0** остаётся `🟡` при терминальных items — снимается `task:plan-close … P0`
  (открыто с ранних handoff'ов, вне фазы P4).

**Sources of truth:**

- `phases/P4.md` — `## Phase Context` (переопределённый вход, контракт фазы, порядок),
  `## Phase Status` (5 items, P4.4 `🟢`), P4.4 ТЗ + Completion Notes.
- `plan.md` — §0 Meta (v1.21.1), §3 Routing (строки P4.1–P4.5), §4 Status Board (`P4 1/5`),
  §7 Contracts Exported (`plan-protocol@2.15.0`, `skiller@0.8.0`, item-коммит `4ca7af67`),
  D89–D93 (§5), §6 Update Log.
- `research/10-p4-entry-gate-and-composition.md` — основание решений захода, в т.ч. § 6
  (долги с носителями, вход packet'а P4.3) и § 8 (pre-mortem).
- `phases/P3.md` § `## Phase Handoff` + `findings/P3.11-terminal-audit-2.md` — фактический
  вход фазы (что доказано / что не доказано, с числами).

**Open risks:**

1. **Приёмка формально не выполнена и не будет выполнена этим планом** (D88/D89): `F1 = 0.96`,
   `F10 = unknown`, layer-2 на знаменателе `5/31`, `F6` на знаменателе 1. Носитель ремонта —
   будущий producer layer-2, вне этого плана; packet обязан назвать это первым.
2. **Гейт P4.4 может покрасить чужой живой план флота**, если его items закрываются после
   cutoff без кодов границ. Измерено этим item'ом: `bash packages/task/scripts/validate.sh`
   по ВСЕМ 14 планам репо — `0 ошибок` (никакой существующий план флота не покрашен; cutoff
   `2026-07-27` строго в будущем относительно всех items флота на момент закрытия). Дальнейшая
   реакция при появлении реального красного — измерить и напечатать список, НЕ смягчать
   правило и не двигать cutoff (Code Guidance P4.4); владелец красного — владелец того плана.
3. **Якорь `Updated`**: если колонка систематически не заполняется/несёт не-ISO форму — item
   обязан остановиться и эскалировать D#-записью выбор якоря, а не подменить его тихо. Не
   сработало в этом прогоне (измерено 0 ERROR по флоту).
4. **Ф2 закрывается ПРИЧИНОЙ, не экземплярами**: запись закрытых items P0–P3 не правилась —
   P4.4 не тронул ни одной записи P3.6–P3.10 (только правило `plan_lint` + канон).
5. Остаточный lint вне диффа: 0 ERROR при 1 WARN (строка Update Log P1.4, 303 символа при
   пороге 300) — открыт с предыдущих handoff'ов, не тронут этим item'ом.
6. Долги без носителя в этом плане (D92): producer layer-2 · расширение наблюдаемости карты ·
   канал `owner_question` · Codex-сторона · CLI-подключение `analyst metrics`/системного
   `skiller eval` (новая публичная поверхность — проектирование, не долг-хвост) · промоушен
   D83 в канон eval-дисциплины · остатки A1 (F11) и A2.

**Workarounds / Deferred / Open questions:**

- Ф3 (одна строка формулировки `findings/P3.10-layer2-paired.md:29`) и Ф4 (переатрибуция
  производителя layer-2 в замороженном манифесте — только через § Correction procedure
  владельца P0.3) остаются записью; отдельных заходов не стоят.
- Посторонний untracked-каталог `.swissknife/` в рабочем дереве — не тронут этим item'ом.
- `docs-sync` follow-up (`packages/task/CLAUDE.md`, описание compiler/enforcement seam) — долг
  P3.1, не тронут; ближайший естественный носитель — P4.3 (docs), если попадёт в его Scope.
- Открытых вопросов со статусом ≠ `Resolved` этот item не оставил.
