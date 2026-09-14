# Локальный релизный draft 0.16.2 — 2026-09-14

Статус: подготовка и qualification GREEN; доставка BLOCKED до обращения к targets.
Тег, commit, push, публикация и PR в этой сессии не создавались.

## Версии и область изменений

| Release unit | До | После | Основание patch |
|---|---|---|---|
| umbrella | 0.16.1 | 0.16.2 | Совокупный локальный релизный draft |
| task | 0.16.1 | 0.16.2 | Исправление continue-root, Next и launch boundary |
| core | 0.16.1 | 0.16.2 | Исправления anti-drift и plan-protocol |
| general | 0.13.3 | 0.13.4 | Те же канонические skills принадлежат также general |
| package.skiller | 0.14.1 | 0.14.2 | Runtime surface включает изменённый configs/publication-versions.json; API не изменён |

Сравнение построенных release surfaces с Git source `v0.16.1` подтвердило ровно четыре
изменённых units и 52 byte-identical units. Private repository-bootstrap не является
распространяемым unit и не требует отдельного bump.

Канонические версии: `packages/skiller/configs/publication-versions.json`,
`packages/skiller/package.json`, `packages/task/configs/command-routing.json` и
`packages/task/.claude-plugin/plugin.json`. npm lock обновлён штатным
`npm version 0.14.2 --no-git-tag-version --ignore-scripts`, зависимости сохранены.
Provider manifests, locks, runtime canon, fixtures, registry и документационные проекции
перегенерированы через `skiller registry`, `render-provider-commands.py --write --repair-owned`
и `scripts/docs-sync.sh`.

## Проверки

- Skiller `scripts/validate.sh`: exit 0, 671 тест; настоящий Codex consumer-acceptance GREEN
  (`codex-cli 0.154.0`), CORE resident budget 431 / 750.
- Task `scripts/validate.sh --fleet`: exit 0, 1073 теста; fleet lint 0 errors,
  3 advisory warnings; `plan-lint --conflicts`: 0 расхождений.
- Core unittest: exit 0, 282 теста.
- `skiller registry --check`: GREEN.
- `render-provider-commands.py --check --root .`: no-op GREEN.
- `scripts/provider-docs.py --check`: GREEN.
- `skiller attest --release v0.16.2 --previous v0.16.1 --check`: GREEN, 56 units.
- `scripts/verify-tag.py v0.16.2`: GREEN по заголовку CHANGELOG и attestation;
  эта проверка не доказывает существование git-тега.
- VitePress standalone Skiller, standalone Task и umbrella: exit 0.
- `git diff --check`: GREEN.

Унаследованные предупреждения Skiller о listing budgets и VitePress о chunk size остаются
предупреждениями, не skipped/failed checks. Дополнительные product docs для bump не нужны:
процесс/API не изменены, существующие Task docs синхронизированы штатным генератором.

## Workflow и фактический блокер

`skiller release --dry-run` сообщил отсутствие conventional commits после `v0.16.1`:
изменения находятся в working tree. SemVer выбран по фактическому diff, а draft-заголовок
CHANGELOG сгенерирован существующей функцией `skiller.release._release_changelog`.
`skiller attest --release v0.16.2 --previous v0.16.1` создал
[`releases/v0.16.2.json`](../../releases/v0.16.2.json).

`skiller deliver --release v0.16.2 --all --dry-run` завершился exit 1:

```text
ERROR: DELIVERY_FAILED: Command '['git', 'rev-parse', 'v0.16.2^{commit}']' returned non-zero exit status 128.
```

Документированный в CONTRIBUTING release/attest/deliver workflow допускает delivery после
тега; код `delivery.deliver` требует существующий release ref на HEAD даже для dry-run.
Локального pre-tag режима нет. Создание тега явно запрещено владельцем; этот gate не обходился,
иной workflow для записи consumers не подставлялся. Apply не запускался, delivery receipt
GREEN отсутствует, потребители и native caches не обновлены.

Read-only inventory охватил 22 уникальных зарегистрированных consumer roots, исключив source
repository. Полные source-bound snapshots — в [`consumer-readback.json`](consumer-readback.json).
Расхождение с draft показывает bytes, ожидающие поставки; само по себе оно не доказывает
ownership conflict. Native Codex core/task установлены как 0.16.1, draft-кэши 0.16.2 отсутствуют.
Неизвестные и неуправляемые targets не изменялись.

После отдельного разрешения на tagged source требуется повторить штатный dry-run, apply
и digest readback; текущие проверки не означают завершённую доставку или обновлённую loaded session.

Полные validation/build/dry-run логи сохранены рядом в `logs/`.

## Повторная проверка agelto, corex, flexcrm, edufy

Свежий `skiller status --json`, проверки всех локальных skill folders и digest readback —
[`four-projects-check.json`](four-projects-check.json). Scope: интеграция Task/Skiller,
application runtime не тестировался. Изменений в проектах не делалось.

- Все четыре Claude marketplace sources корректны, missing/extra по конфигу нет.
- agelto явно выбирает Codex disabled: отсутствие project Codex bundles соответствует конфигу.
- corex, flexcrm, edufy: все Codex surfaces совпадают с attestation 0.16.1,
  SKM provider locks читаются и совпадают с установленными bytes. Только core/task
  расходятся с draft 0.16.2; оба installed project bundles имеют версию 0.16.1.
- agelto, corex, edufy: мёртвых локальных skill entries нет.
- flexcrm: 41 dangling symlink в `.claude/skills`, 41 в `.cursor/skills`, 8 в
  `.agents/skills`; они ведут к отсутствующим `.ai/skills/<name>`. В этих каталогах
  отсутствует managed vendor manifest, поэтому ссылки не удалялись и не перевендоривались.
- corex/flexcrm/edufy: status отмечает `SKILL_REQUIRED_EXCLUDED` для
  session-observer → shared-memory из общей DEFAULT_EXCLUDE policy. Файл shared-memory
  фактически присутствует в доставленных system bundles; это предупреждение policy,
  а не доказательство отсутствующего runtime-файла.
- Source listing estimate Codex превышает fallback threshold 8000 characters:
  corex 16428, flexcrm 28632, edufy 17134. Реальная загрузка provider в этой проверке
  не измерялась. Вывод status для выключенного Codex agelto не является active budget gate.

Итог: release 0.16.1 project artifacts целы; delivery 0.16.2 ожидает source tag gate.
flexcrm дополнительно имеет подтверждённые unmanaged dangling links.

## Последующее явное поручение: включить Codex в agelto и упростить flexcrm

Выполнено после исходной release-preflight проверки, по отдельному запросу владельца.
Это project configuration через Connect и native CLI, а не обход tagged release delivery.
Предыдущие readback snapshots выше сохранены как историческое состояние.

- agelto: Codex enabled, 9 выбранных plugins; добавлен project `.codex/config.toml`.
- flexcrm: набор 23 → 15 plugins. База agelto плюс frontend-backend, frontend-naive-ui,
  frontend-tailwind, frontend-wayfinder, frontend-nuxt, frontend-vue. Выбор проверен по
  manifests корневого legacy Inertia и уже существующих `frontend/`/Nuxt layers.
- 90 dangling legacy links flexcrm архивированы с сохранением исходных symlink targets:
  Claude 41, Cursor 41, Codex 8. Живые project skills и изменения приложения сохранены.
- Перед apply выполнен Connect dry-run обоих проектов. Обнаруженный Skiller bug
  `record-provenance-mismatch` при замене набора устранён в owning connect.py:
  dry-run рассчитывает post-prune snapshot, prune проверяет все owned preimage digests
  до удаления и сохраняет чужие owner records. Добавлены regression tests на замену без
  consumer writes в dry-run и отказ при изменённом preimage до любых writes.
- Project bundles core/task теперь 0.16.2 с digest readback GREEN; native core/task
  остаются 0.16.1. Шесть неизменённых frontend units установлены в native cache как 0.4.0,
  каждый cache совпадает с историческим release attestation. Они выключены в user default
  и включаются локальным конфигом flexcrm; все прежние global config значения сохранены.
- Native `plugin list` из consumer совпадает с выбранным набором: agelto 9, flexcrm 15.
  Offline `debug prompt-input` содержит все declared native skill identities: 69 и 90.
- Source-bound project readback: GREEN на 11/17 поверхностях; dangling local entries: 0.
  Codex settings doctor: clean. maind health: connected, provider trust GREEN у обоих providers.
- First-turn estimate: agelto 11199, flexcrm 14813, verdict OK. Это оценка footprint,
  а не заявление о фактической оплате или исчерпывающем provider loading measurement.
- Claude settings doctor: exit 1, error 0; унаследованные user/local warnings сохранены
  в evidence. Они включают stale additionalDirectories и разницу effective permission mode
  с настройкой VSCode flexcrm. Изменение permissions не требовалось для выбора plugins.
- Полная validation Skiller после owning fix и registry regeneration: 673 tests,
  consumer-acceptance GREEN; source attestation draft перегенерирован штатным attest.
  Остальные ранее пройденные package checks сохраняют scope: Task/core runtime не изменён.

Полный итог с readback, бюджетами и doctors —
[`project-setup-result.json`](project-setup-result.json); rollback preimages —
`~/.swissknifeman/receipts/setup/20260914T075645Z-agelto-flexcrm/`.
Документация project activation обновлена в agelto/flexcrm и canonical project-tooling-runbook;
официальная config reference и локальная CLI проверка записаны в `docs/reference.md`.
Release tag/push/publish/PR не создавались. Tagged native delivery 0.16.2 остаётся отдельным gate.
