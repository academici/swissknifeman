# analyst — continuous learning экосистемы academici

Детерминированный (stdlib-only, **on-demand — без демона**) слой, который накапливает
«выстраданные уроки» из потоков задач Claude Code сразу по всем проектам экосистемы и —
**с человеком в гейте** — превращает их в переиспользуемое знание (память mAInd → скиллы).
Не отдельный анализатор в каждом проекте, а ОДИН слой поверх многих пакетов и проектов.

> Реализованный контур: **P1 (MVP)** — `digest` + lessons-store + human `review`/`promote`;
> **P2** — cross-project агрегатор `scan`; **P3** — confidence-арифметика (Beta/decay) +
> числовая state-machine `recompute` + mem0-таксономия; **P4** — `suggest` → ЧЕРНОВИК скилла
> (`SKILL.ru.md` в staging, промоут — человек). Дальше по roadmap: `analyst-capture` + `observe.sh` (P5).
>
> 📖 Документация: [`docs/`](docs/) (VitePress — standalone + зонтичный агрегат).

## Почему так (анти-collapse)

Наивное «обучение-на-себе» вызывает *model collapse*. Доказанный антидот — **self-verification**
+ **никогда не выбрасывать ground-truth** (человеко-подтверждённые якоря). Поэтому human-gate +
провенанс + validate-before-promote — не осторожность, а достаточное условие против деградации.

## Поток данных (MVP)

```
<project>/.claude/runs/<sid>.json          (run-report — пишет SessionEnd-хук harness)
   │  analyst digest → детерминированное извлечение кандидатов (высокоточные сигналы)
   ▼
<project>/.claude/analyst/lessons/{ephemeral,candidate,curated,deprecated}/<id>.json  (LOCAL)
<project>/.claude/analyst/audit.ndjson     (append-only провенанс)
   │  analyst review  → список + diff против активных (Jaccard, stdlib)
   │  analyst promote <id>  → ЧЕЛОВЕК подтверждает → state++ → audit
   ▼  (curated) → maind memory → всплывает на SessionStart (memory-digest-hook)
```

**Инвариант приватности:** сырьё (raw-транскрипт) — LOCAL-only; наружу идёт только
абстрагированный урок (trigger+action+evidence). Секреты — только по ссылке, никогда значение.

## Команды

```bash
analyst digest    [--cwd | --session UUID]      # run-report → кандидаты в ephemeral/
analyst review    [--state ephemeral|candidate|curated] [--json]
analyst promote   <id> [--to candidate|curated] [--yes]   # human-gate; curated → память mAInd
analyst deprecate <id>                          # soft-демоут (не удаляется — аудит)
analyst doctor                                  # диагностика окружения
analyst workflow-scan --output DIR --now ISO    # read-only workflow fleet evidence
```

## Разработка

```bash
bash scripts/test.sh          # unittest (без сети и демонов)
bash scripts/validate.sh      # py_compile + bash -n + JSON + обязательные файлы + тесты
```

stdlib-only; `Env(BaseEnv)` явно; atomic JSON; сообщения на русском. Конвенции — в `CLAUDE.md`.
