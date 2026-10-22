# Остатки «хвостов аудитов» 2026-10-20 — отложено с триггерами

Статус: идеи, не начаты. Источник: файл задачи «хвосты аудитов» 2026-10-20 (workspace tasks, вне git) — работы W1–W10 выполнены
20 Oct (коммиты `5754e93a4` … `0f826a9a6`). Сверено с PLAN9 и `stable/p4` 22 Oct. Здесь — только то, что после
удаления исходного файла иначе потерялось бы. Уже покрытое PLAN9 — ссылкой, структурные отказы — в
`docs/rejected-optimizations.md`.

## Отложено до триггера

| Предложение | Вернуться, когда |
|---|---|
| model-capability/v2, scoring, shadow/advisory/canary routing (O6–O7) | ≥ 30 завершённых попыток на пару role×provider×model с исходом и стоимостью за 2 недели (отчёт analyst) |
| Circuit breaker, provider health, probed capabilities (O18) | ≥ 3 run за 2 недели, остановленных серией transport/provider_internal ошибок одного провайдера |
| Multi-repo подписанные GUI catalogs, Level-2 UI (O20) | первый модуль `destination: own-repo` публикует gui.json из своего репозитория |
| GUI: retry graph, reconciliation queue, policy simulator, instruction/artifact explorer | измеренная нужда (timeline сделан в W7, health — P8.3) |
| Quorum ревью (второй reviewer на пункте, S4) | запрос второго reviewer на одном пункте |
| Полная conformance-матрица ошибок провайдеров (O21) | обновление CLI провайдера ломает разбор в run (схема conformance-report — P4.3) |
| Fault-injection: диск полон на checkpoint; журнал записан, проекция нет; завис плагин; смена JSONL CLI; модель исчезла между prepare и launch | первый такой случай в журнале (основное покрыто P8.2, P5.1) |
| Настраиваемый лимит 64 КиБ данных события `emit` | первый усечённый полезный payload; нужен способ отдать конфиг `emit` без чтения TOML на каждое событие |
| context-bundle/v2, soft-бюджеты condense/downgrade (O11) | доля Stop `PROVIDER_CONTEXT`/`TOKEN_BUDGET` > 10 % модельных стадий за 2 недели (condense — P6.6) |
| Отдельные timeouts launch/readiness | первое зависание старта, которое не поймали idle/progress (P8.1) |
| Material descriptors, citations (S7) | материал > 1 МБ или бинарный вход (R2, P9.6) |
| Config: deprecated-key, `config migrate` | первое переименование ключа (P10.1/P10.5) |
| Копия input.json без acceptance-команд | только при `access=confined` |

## Хвосты самого W

- **W3.6** не воспроизведён (источник `/tmp/.git`, `/tmp/.swissknifeman`, коммит `c1b3ae729`) — вернуться при повторе.
- **W4.5** сделан в слабой форме: prune называет удаляемые локальные evidence, но удаляет.
- **W10.3**: исторические строки CHANGELOG (165/189/191/196) ссылаются на удалённые `audits/…`, `ideas/plan-review-strictness.md`,
  `ideas/workspace-audit-deferred.md`; `packages/skiller/configs/selection-summary.json:3` — на `audits/perplexity-audit.md`.
  Исторические записи CHANGELOG не переписывать; provenance skiller поправить при следующей правке skiller.

## Конфликт, разрешённый сверкой

Строка «`executor_runs_checks: true` по умолчанию — дефолт false по замеру PLAN8 P1.2/P2.1» излагала замер наоборот:
P1.2 с `false` — 3 круга проверок (2 красных, причины ловились целевыми тестами), P2.1 с `true` — зелёный с первого
раза (выборка из одного; `git show 22f7dae39:reports/skm-changes-run-log.md`). `false` держится ради стоимости
(полный прогон исполнителем — 30–50 % его шага). Решение задачи `2026.10.04-execution-loop-repair` T1: приёмка у
conductor, дешёвая самопроверка у исполнителя; новый замер — P4.3.

## Только владелец (§5 исходного файла, проверено 22 Oct)

- [ ] Отозвать и перевыпустить GitHub-токен, вставленный в чат при прогонах edufy (2026-10-18) — с машины не проверить.
- [ ] Rootful Docker: пользователь в группе `docker`, сервис `docker` active, контекст `default → /var/run/docker.sock`;
      команды — `packages/orch/docs/docker-environment.md:108,146-151`.
      22 Oct: rootful ещё обслуживает живые базы commerz и azguard (5 контейнеров, тома 11 ГБ), rootless пуст —
      сначала перенести проекты на rootless, затем `systemctl disable --now`, позже prune и выход из группы.
- [x] (удалены владельцем 22 Oct) Временные файлы: `~/.sk-sock-test/`, `/tmp/sk-sock/`, `/tmp/claude-1000/chatom-local-backup/`,
      `swissknifeman/.claude/settings.local.json.bak`.
- [ ] Workspace axioma: 35 незакоммиченных путей — `workspace sync --commit`.
- [ ] План edufy: обходные `orchestration` P1.1–P2.3; формулировка `plan.py finish`; `depends_on` P1.2–P1.4;
      frontier на sonnet (P3.2, P4.4, P4.12, P5.10); находки ревью P2.6 (F1–F3, тест `government`).
