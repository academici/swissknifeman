# Уточнения владельца

## 2026-07-19 — синтаксис запуска task-команд в ChatGPT/Codex

- В текущей ChatGPT/Codex surface task-команда запускается через `$ task:plan-design …`:
  после символа `$` обязателен пробел. Рекомендация в Claude-форме `/task:plan-design …`
  здесь приводит к сообщению «команда не найдена».
- Финальные рекомендации и `handoff.md`, адресованные текущей Codex-сессии, должны давать
  копируемую команду в форме `$ task:…`. Внутренний semantic command ID не меняется.
- Долгоживущий provider-neutral command/invocation contract проектируется в P4; P3 отвечает
  только за доставку skill/plugin identity и не переписывает task semantics.

RAG:— (owner-grounded: прямое уточнение владельца в сессии 2026-07-19).

## 2026-07-19 — границы design-захода P4

- Детализировать только P4; соседние фазы не разворачивать.
- Package code в design-заходе не исполнять.
- `plans/2026.07.18-FOREMAN` и fleet не менять.

RAG:— (owner-grounded: прямое ограничение запуска P4 в сессии 2026-07-19).

## 2026-07-19 — границы design-захода P5

- Детализировать только P5; P6/P7 и соседние фазы не разворачивать.
- Cold-start источниками считать явно переданный набор plan/P4/P5/brief/research/contracts;
  read-only recon `packages/harness` допустим только для конкретизации design.
- Package code/items не исполнять; допустимы только правки plan artifacts и plan-lint.
- `plans/2026.07.18-FOREMAN`, `plans/ACTIVE.md`, root bootstrap surfaces и fleet не менять.

RAG:— (owner-grounded: прямое ограничение запуска P5 в сессии 2026-07-19).

## 2026-07-19 — границы design-захода P6

- Детализировать только P6; P7 и соседние фазы не разворачивать.
- Cold-start источниками считать явно переданный набор plan/P5/P6/brief/research/contracts;
  read-only recon `packages/maind`, `packages/analyst`, `core` и current harness run-report
  допустим только для конкретизации исполняемого design.
- Package code/items в design-заходе не исполнять; допустимы только чтение, правки plan
  artifacts и plan-protocol bookkeeping/plan-lint.
- `plans/2026.07.18-FOREMAN`, `plans/ACTIVE.md`, root bootstrap surfaces и fleet не менять.

RAG:— (owner-grounded: прямое ограничение запуска P6 в сессии 2026-07-19; допустимый
read-only recon вытекает из требования детализировать executable P6 без исполнения code).

## 2026-07-19 — границы design-захода P7 и roadmap/model correction

- Детализировать только P7; package code/items не исполнять, FOREMAN/fleet не менять.
- Cold-start источниками считать явно переданный набор plan/P6/P7/brief/research/contracts.
- Полная детализация P7 завершает все фазы, поэтому создать `2026.07.19-DUAL-PROVIDER/roadmap.md`
  по каноническому формату; `plans/2026.07.18-FOREMAN/roadmap.md` использовать только как
  read-only образец и не изменять.
- Routing и roadmap должны называть подходящие актуальные модели ChatGPT/Codex как
  исполнителей плана, а не Claude model names.
- Для финального cross-phase design/verification использовать мощный ChatGPT/Codex tier:
  GPT-5.6 Sol с xhigh reasoning; prescribed implementation направлять на GPT-5.6 Terra.

RAG:— (owner-grounded: прямые уточнения владельца в сессии 2026-07-19). Актуальная
model-family проверена отдельно в `findings/P7-openai-model-routing-2026-07-19.md`.

## 2026-07-19 — границы finish design pass 3/3

- Выполнить финальный cross-phase reconcile P0–P7 по явно переданному cold-start набору:
  plan/roadmap, все phase files, brief и ключевые research syntheses.
- Сверить phase contracts, конечность/порядок Required Reads, per-item Routing и owner gates;
  завершить design pass 3/3 и подготовить следующий независимый design audit.
- Package code/items не исполнять; допустимы только plan artifacts, bookkeeping,
  verification capture и plan-lint.
- `plans/2026.07.18-FOREMAN/**` и fleet не менять.

RAG:— (owner-grounded: прямой запуск `task:plan-design 2026.07.19-DUAL-PROVIDER finish`
в сессии 2026-07-19).

## 2026-07-19 — remediation после RED design-аудита

- `AGENTS.md` должен быть семантическим Codex-аналогом `CLAUDE.md` на root и package
  уровнях. Оба представления строятся из общего канона правил; байтовая идентичность
  не требуется, provider-specific additions разрешены как явные extensions.
- Нужен исполнимый carrier общего instruction contract: canonical source, root/package
  projections, managed sections, extensions, provenance/source hash и gates semantic
  parity/drift/repair/backward compatibility.
- Механизм должен быть создан в P5/P6; P7 только проверяет self-host, cleanup и release.
- Restart durability трассируется на фактические P6.5/P6.6 carriers, не P6.4.
- Journal остаётся append-only: старые строки не переписываются, незавершённые lifecycle
  pairs получают terminal backfill/correction records.
- В этом remediation package code/items, package tests и plan-lint не запускаются;
  без нового anchored plan-lint нельзя заявлять GREEN. FOREMAN, ACTIVE и fleet не менять.

RAG:— (owner-grounded: прямой remediation-запуск после audit-red 2026-07-19).

## 2026-07-19 — remediation повторного design audit, F1 journal lifecycle

- Режим — remediation audit-r2, не execution; первым входом является
  `findings/design-audit-2026-07-19-r2.md` F1.
- Owner-gated устранить противоречие append-only history и strict per-line schema;
  выбрать исполнимую нециклическую correction/supersession semantics либо явное
  provenance-preserving exception.
- Синхронизировать journal writer/schema/linter/plan lifecycle и получить current anchored
  `0 ERROR / 0 WARN`; затем подготовить новый design audit, не запускать P0.1.
- Не менять P0.1–P7.4 implementation/items, `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`,
  fleet и unrelated changes; instruction remediation P5.6→P7 не менять, кроме journal-gate ссылок.

RAG:— (owner-grounded: прямой запуск remediation audit-r2 2026-07-19).

## 2026-07-20 — точечная remediation design audit r3, F1 same-plan invariant

- Режим — remediation audit-r3, не execution; первым входом является
  `findings/design-audit-2026-07-19-r3.md` F1.
- Связать event и exception `plan_id` с canonical ID текущего plan directory в writer и
  linter; mismatch остаётся non-exemptable ERROR и не подавляется sidecar.
- Добавить writer/linter negative tests для foreign event/sidecar IDs и exact field-set;
  воспроизвести current `0 ERROR / 0 WARN` и wrong-plan nonzero.
- Lifecycle canon/research/D# синхронизировать только при изменении contract; подготовить
  новый design audit без запуска P0.1.
- Не менять P0.1–P7.4 implementation/items, package seams вне task journal/linter/tests и
  plan-protocol journal lifecycle, FOREMAN, ACTIVE, fleet, instruction remediation P5.6→P7
  и unrelated user changes.

RAG:— (owner-grounded: прямой запуск remediation audit-r3 2026-07-20).
