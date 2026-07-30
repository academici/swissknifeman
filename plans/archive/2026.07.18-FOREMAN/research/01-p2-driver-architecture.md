---
type: research
plan: 2026.07.18-FOREMAN
phase: P2
date: 2026-07-18
inputs:
  - ../findings/owner-deep-audit-skills-2026-07-18.md
  - ../findings/perplexity-supervisor-patterns-2026-07-18.md
  - ../findings/headless-claude-code-factsheet-2026-07-18.md
  - ../phases/P0.md
  - ../phases/P1.md
---

# P2 — архитектура CLI-драйвера Artifex (синтез детализации фазы)

Слой-2 синтез поверх findings (owner-deep-audit, supervisor-patterns, headless-факт-лист)
и запечатываемых контрактов P0/P1. Каждое несущее решение → D-запись в plan.md §5.

## 1. Язык и раскладка пакета (→ D25)

**Python stdlib**, не Rust. Обоснование:
- Reuse-мандат D15а: cost/turns из `_usage.py`, парсинг транскрипта из `_lib.py` — обе
  Python (repo-grounded: `packages/harness/configs/claude-code/hooks/run-report/`). Драйвер
  на Rust потребовал бы порт этих модулей — против reuse-гейта.
- Конвенция SKM: `task`/`skiller`/`maind`/`analyst` — Python stdlib-only (repo-grounded:
  `packages/task/scripts/validate.sh` — `python3 -m compileall`; `packages/skiller/lib/skiller/`).
- ralph-orchestrator (Rust, D15а/D17а) — АРХИТЕКТУРНЫЙ референс (внешний демон +
  персистентный state между запусками), НЕ донор кода.

Раскладка — зеркало `skiller` (единственный SKM-пакет с CLI):
```
packages/artifex/
├── bin/artifex              # тонкий bash-лаунчер → python3 -m artifex (образец: bin/skiller)
├── lib/artifex/             # весь код (импортируемый, тестируемый)
│   ├── __init__.py __main__.py cli.py
│   ├── plan_reader.py       # чтение состояния плана по parse-контракту P0.2
│   ├── worker.py            # запуск claude -p, defensive JSON parse
│   ├── decision.py          # handoff.Next форма → действие драйвера
│   ├── run_folder.py        # state.json/journal.jsonl/resume (схема P0.6)
│   └── retry.py             # 3-классовая лестница (tier1/2/3, D18)
├── scripts/validate.sh      # образец: packages/task/scripts/validate.sh
├── tests/test_*.py
├── .claude-plugin/plugin.json
└── CLAUDE.md
```

## 2. Владение записью журнала (reconcile D24 → D26)

D24 говорит «Artifex-прогон пишет в ОБА журнала». Во избежание двойной записи одной строки
разграничение владельца:

| Журнал | Схема | Кто пишет | Когда |
|:--|:--|:--|:--|
| пер-плановый `plans/<ID>/journal.jsonl` | P1.1 | **воркер** (close-протокол plan-exec, хелпер `lib/task/journal.py`, P1.3) | одна запись на исполнение item (старт+финал) |
| run-folder `runs/<код>/journal.jsonl` | P0.6 | **драйвер** | событийно (launch/retry/escalate/quota-pause/decision) |

Связь: драйвер инъектит `run_id` в окружение воркера (env `ARTIFEX_RUN_ID`) → воркерская
пер-плановая запись несёт `run_id` (P1.1 поле nullable: ручной запуск → null,
Artifex-порождённый → set). Так «пишет в оба» соблюдается: run-folder — драйвером, пер-плановый —
порождённым воркером, оба линкуются `run_id`.

**Бэкфилл-исключение:** если воркер УПАЛ до close-протокола (crash/timeout/quota-abort — нет
пер-плановой записи), драйвер САМ дописывает пер-плановую запись (`result` = `blocked`/`escalated`,
cost из захваченного JSON `--output-format json`), чтобы история плана не имела дыр. Это
единственный случай, когда драйвер пишет в пер-плановый журнал напрямую (роль backstop-хука D21,
исполняемая супервизором).

## 3. Решающая логика драйвера: handoff.Next форма → действие (потребляет P0.2)

Драйвер читает `handoff.md` поле `**Next:**` (форма — по первой непустой строке, P0.2
parse-контракт) и Status Board. Дефолт MVP (конфигурируемо через policy P0.3):

| Форма Next | Действие драйвера |
|:--|:--|
| `/task:plan-exec Pn.m [Pn.k …]` | **DRIVE** — spawn воркера (если фаза в скоупе мандата) |
| `/task:plan-close <ID> Pn[.m]` | **DRIVE** — механический self-contained close (sonnet/low) |
| `/task:plan-run Pn.m` | **ESCALATE** — manual-item, модель наследуется сессией; драйвер не угадывает модель |
| `/task:plan-audit …` · `/task:plan-design …` | **ESCALATE** — owner/opus-гейт (аудит адверсариальный) |
| `«ЗАПУСК ВРУЧНУЮ: …»` | **ESCALATE** — Exec=manual, opus/fable |
| `«ОЖИДАНИЕ: <условие> → …»` | **WAIT** — таймер/гейт до условия, затем перечитать |
| `«план закрыт»` | **DONE** — мандат исчерпан, финальный отчёт |

Консервативность (D10 «сомнение → эскалация»): драйвер авто-ведёт ТОЛЬКО `plan-exec`/`plan-close`;
любой иной джанкшн → пауза+эскалация владельцу. Soft/hard-параллелизм по DAG (idea #1
owner-deep-audit) — P5, не MVP. Граница скоупа мандата: Next в фазе вне мандата → стоп («мандат
исчерпан»). → D27.

## 4. Reuse-карта (что берём готовым)

| Нужда | Источник | Как |
|:--|:--|:--|
| cost_usd / num_turns прогона | `_usage.py` (`iter_jsonl`/`feed_event`/`finish`) | импорт по пути run-report, не свой парсер |
| парсинг транскрипта (форензика при сбое) | `_lib.py` (`parse_transcript`) | библиотека, «1 сессия = 1 item = 1 run-report» (D15а) |
| внешний цикл + персистентный state | ralph-orchestrator layout | шаблон структуры run-folder (D17а), не код |
| event-JSONL + таймаут-деградация | obra/claude-session-driver | идея (D15а), не tmux-механизм |
| дефенсивный JSON-контракт | supervisor-patterns §Консенсус | `type==result`+`is_error`+exit, не stdout |

Кросс-пакетный импорт run-report (harness → artifex): если прямой импорт нежелателен —
скопировать минимальную функцию с провенанс-комментарием (та же дилемма, что P1.3;
package-contribution-protocol: минимальный контракт, не тянуть весь harness).

## 5. Устойчивость (P2.4)

- `state.json` — атомарная запись (temp-file + `os.replace`): crash посреди записи не бьёт файл.
- resume-by-folder (D16): `artifex continue <папка>` → перечитать `brief/00-mandate.md` → `state.json`
  → хвост `journal.jsonl` → продолжить с прерванного item. Незавершённый item НЕ резюмится
  (сессии эфемерны) — перезапускается свежей сессией.
- Идемпотентность повторного `continue`; тест «kill -9 посреди item → continue → корректное
  продолжение» (P2.4 Validation).
</content>
</invoke>
