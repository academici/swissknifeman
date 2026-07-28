# HANDOFF — 2026-07-28 — after P6.1

**P6.1 закрыт `🟢 Done`** (`0c711cce` — item-коммит): в harness заведена поверхность
`configs/claude-code/statusline/` — рендерер `модель · каталог · бар · N%` + детектор
пересечения полосы порога (дефолт `80,90`, кулдаун 15 мин), который отсоединённо (`setsid`)
дёргает СУЩЕСТВУЮЩИЙ `hooks/notify/notify.sh` (второго нотификатора не заведено). Состояние
на сессию пишется атомарно (`tmp`+`mv`), `used_percentage: null` не считается нулём.
Включение opt-in per-project: `harness hooks --target . --statusline context|off` (ключ
`statusLine` в `settings.local.json`, чужое значение уважается skip+warn); файлы ставит
ветка `--global`. Четыре доказательства сняты числом: дельта `skiller budget --first-turn`
**0 ток** (2547 → 2547), латентность **медиана 5.4 мс / максимум 6.9 мс** на 50 прогонах
(порог 50/150), офлайн-таблица полос (`COOLDOWN_MIN=0` → ровно 3 уведомления,
`COOLDOWN_MIN=15` → ровно 1, подавленный алерт не съеден), ноль сирот доставки + живой
прогон реального `notify.sh`. Детали — `findings/P6.1-statusline-measure.md` и
`phases/P6.md` P6.1 Completion Notes.

**Next:** фаза P6 не терминальна (2/3) — остался **P6.3** (`Exec = manual`,
`implementation/high`, solo). Он **блокирует P2.3** (производит спеку `research/14`
пункта DoR, D81), поэтому идёт вперёд P7.

| Параметр | Значение |
|:--|:--|
| Model | sonnet — предписано Routing (`implementation/high`) |
| Thinking | high — предписано Routing, не sonnet/medium |
| Context | continue (/clear) — ручной item |
| Суть | P6.3: три дельты anti-overconfidence в `verify-claims` + абзац в корневом `CLAUDE.md` + три pressure-кейса + спека пункта DoR |

**ЗАПУСК ВРУЧНУЮ: sonnet/high** (`Exec = manual` — деривация §9: `effort > medium`;
`/task:plan-exec` пинит sonnet/medium и обязан такой item отклонить):

```
/model sonnet
/effort high
/task:plan-run 2026.07.25-ECO-OPT P6.3
```

**Done:** **46/52 items терминальны** (29 🟢 · 16 🟠 · 1 ⛔). Закрыты фазы **P1** (1/2, 🟢),
**P3** (2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9** (3/4, 🟠),
**P10** (1/4, 🟠), **P11** (6/8, 🟠); частично — **P6** (1/3, 🟡 — не терминальна).

**Remaining:** 6 items: P2.2/P2.3 · P6.3 · P7.1–P7.3. Порядковые условия: P2.3 — ПОСЛЕ P6.3
(D81/D93) и ПОСЛЕ P8.1/P8.2/P8.3 (терминальны); P7.1 + P7.3 → P7.2. Условие P6.1 (ПОСЛЕ
P9.1) снято его закрытием.

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index — `P6 1/3`; §6 Update
Log — запись закрытия P6.1) · `phases/P6.md` (Phase Status + P6.1 Completion Notes) ·
`findings/P6.1-statusline-measure.md` (все числа замеров) ·
`packages/harness/configs/claude-code/statusline/**` · `packages/harness/lib/harness/hooks.py`
(`block_statusline`) · `packages/harness/scripts/apply-permissions.sh` (ветка `--global`) ·
машинные гейты `packages/harness/scripts/validate.sh`, `packages/harness/scripts/test.sh`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей, записи (40)–(43)) плюс:
(44) **отмена statusline-скрипта на середине не наблюдалась** — рендер ~5 мс против 300 мс
дебаунса, окно отмены на такой длительности не воспроизводится. Свойство закрыто
КОНСТРУКЦИЕЙ (отсоединённая доставка + атомарное состояние + регресс-тест на отсутствие
`*.tmp`), а не наблюдением; выдавать это за проверенное нельзя.
(45) **таймаут statusline-скрипта остаётся `[UNVERIFIED]`** (дока его не называет,
`findings/P6-context-hygiene-facts.md` §1.4) — бюджет времени по-прежнему самодисциплина.
(46) **латентность снята на одной машине** (Linux); кросс-платформенные ветки доставки
(macOS/WSL) этим item'ом не перепроверялись — `notify.sh` не менялся.

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — без изменений этим заходом (F1 roadmap-кандидат, расхождение flexcrm 142 vs
186, апстрим-URL `oss-dev/to-issues` 404, протокол backup-restore); плюс хук на
`PreCompact`/`PostCompact` остаётся roadmap-кандидатом (в скоуп P6.1 не входил, D53).
· **open questions** — без изменений; OQ-11 остаётся `Decision pending` до закрытия P11.
