# HANDOFF — 2026-07-31 — after P1.1

**Next:** /task:plan-exec 2026.07.31-SKM-LEAN P1.2

Baseline-замер по флоту (P1.2) снимает `--with-plugins`-инклюзивный first-turn по всем
`enabled`-записям реестра (`config.json`) — Routing `implementation/medium`, `Exec = plan-exec`
(модель/effort пинуются командой). Solo-запуск (roadmap.md) — обход исполняет `SessionStart`-хуки
чужих репозиториев, не смешивать с другой работой в той же сессии.

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — пиновано `plan-exec`; разбор `n/a`/stale-строк реестра не механическая правка |
| Context | continue (/clear) — ручной item |
| Суть | Разовый скрипт-обход 26 записей реестра → `findings/P1-fleet-baseline.md` (baseline для порога P1.3) |

```
/task:plan-exec 2026.07.31-SKM-LEAN P1.2
```

**Done:** **P1.1 закрыт → 🟠 Done with deviations.** Session: sonnet/high (Routing
`implementation/high` — точное совпадение, без перебора). Реализован
`packages/skiller/lib/skiller/plugins.py` (перечисление enabled-плагинов через `claude plugin
list --json`, дедуп по `id`, always-on цена через `claude plugin details <id>` с кэшем по `id`,
fail-loud — `tokens=None`/`n/a` на любом сбое, без молчаливого 0) + флаг `--with-plugins` у
`skiller budget --first-turn` (только вместе с `--first-turn`, аддитивные JSON-ключи
`plugins`/`session_total`/`session_verdict`, D16 — контракт `maind doctor --context` не задет).
8 тестов `test_plugins_aggregate.py` зелёных (happy-path/дедуп/exclusion/n/a-без-бинаря/дрейф
формата/warnings/die-без-`--first-turn`/back-compat), фикстуры — дословный вывод живого `claude
2.1.220`, захваченный в этой сессии. Канон `root.claude-code.context-budget` приведён к факту во
всех шести носителях (`harness instructions apply --authorize` на 12 целей, `--check` 12/12
clean); числовая половина порога не тронута — её владелец P1.3. Roadmap-запись
`budget-first-turn-plugin-visibility.md` закрыта (удалена, строка в `roadmap/README.md`).
Item-коммит `487e68d0`, bookkeeping — этим коммитом (см. Commits ниже). Полные Completion Notes
и Validation-протокол — `phases/P1.md` P1.1.

**Единственное material-отклонение:** item-коммит несёт правку `.swissknifeman/provider-artifacts.lock.json`
(1 строка) сверх перечня `Files` P1.1 — прямой побочный продукт мандатного шага `harness
instructions apply` (Implementation Rules §11в), не посторонний дифф и не решение исполнителя
расширить Scope; `Files` P1.1 просто не перечислял этот носитель. Разобрано в Known Deviations
P1.1 с рекомендацией `plan-design` дополнить `Files` P1.3/P2.1/P5.4 (тоже правят этот канон) тем
же носителем.

**Remaining:** P1.2 → P1.3 закрывают фазу P1 (P1.1 закрыт 🟠 — в счётчик «🟢/всего» не входит,
только `Status` item'а; фаза остаётся 🟡 In progress до терминальности всех трёх); затем P2 → P3
→ P4 → P5 → P6 → P7 по `roadmap.md`. Доска: P1 0/3 · P2 0/6 · P3 0/5 · P4 0/6 · P5 0/9 · P6 0/3 ·
P7 0/4.
Восемь items идут `Exec = plan-exec` (P1.2 · P2.4 · P2.6 · P5.2 · P5.3 · P5.6 · P6.3 · P7.2),
остальные 27 — ручным маршрутом (`plan-run` под моделью/effort сессии владельца, D18, при
точном совпадении/переборе Routing — недобор блокируется гейтом).

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/plan.md` (§0 Meta, §3 Routing 36 строк, §5
D1–D78, §6 Update Log, §4 доска P1 0/3) · `phases/P1.md` (P1.1 Completion Notes/Known Deviations
целиком, P1.2/P1.3 без изменений) · `open-questions.md` (OQ-1…OQ-6, OQ-8 — семь открытых, без
изменений) · `roadmap.md` (P1.2 — batch solo) · `findings/P1-plugin-cli-probe-2026-07-31.md`
(вход P1.1, теперь ещё и провенанс фикстур) · `packages/skiller/tests/fixtures_data/plugin-list.json`
и `plugin-details-codex.txt` (дословный вывод `claude` 2.1.220, 2026-07-31) · `roadmap/README.md`
§«Закрыто и удалено».

**Open risks:** (все прежние риски P1–P7 в силе, см. предыдущий handoff — не повторяются здесь,
правило двух SSOT) плюс:

- **Files-пробел канон-items.** P1.1 показал, что правка `root/*` канона задевает
  `.swissknifeman/provider-artifacts.lock.json` побочно (12 рендеров, 1 общий лок-файл) — тот же
  пробел ТЗ, скорее всего, повторится на **P1.3**, **P2.1**, **P5.4** (тоже правят этот канон).
  Носитель не добавлен в их `Files` превентивно — `plan-design` должен свериться перед
  `finish`-подобной правкой, иначе те items тоже закроются `🟠` тем же классом отклонения.
- **`brain@brain` — реальный сломанный плагин в среде исполнителя**, а не фикстура: живой смоук
  P1.1 показал `partial: true`/`unparsed`/`warnings` на КАЖДОМ прогоне `--with-plugins` в этом
  репозитории до починки `~/Vaults/Brain/.claude-plugin/plugin.json` — не блокер P1 (это и есть
  fail-loud поведение по спецификации), но baseline P1.2 обязан явно назвать эту строку, а не
  списать на дрейф формата чужого CLI.

**Workarounds/Deferred/Open questions:** без изменений от предыдущего handoff (P1.1 не
затрагивает workarounds/deferred/open questions плана) — «—» / «—» / OQ-1…OQ-6, OQ-8 (семь
открытых), см. `open-questions.md`.
