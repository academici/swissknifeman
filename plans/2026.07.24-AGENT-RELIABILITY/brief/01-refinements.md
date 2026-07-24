# Refinements — Design Pass 2 — 2026-07-24

## Audit RED, attempt 1

Владелец потребовал полный новый design sweep, а не локальную правку и не
запуск P0. Исправления обязательны:

- neutral Routing по canonical closed enums;
- roadmap с точной таблицей, готовым native Codex `NEW SESSION` carrier для
  каждой solo/batch/workflow-группы и только реальными Owner gates;
- честный счётчик `Design Passes: 2/3`, следующий шаг — новый Pass 3;
- falsifiable RCA: declarative audit/session controls уже существовали, а
  причина их фактического неприменения пока не доказана;
- cold-start evidence: hash/claim inventory внешнего аудита, exact manifest
  семи journals, selected session manifest и deterministic stdlib extractor;
- точные Files/Validation/RAG markers, без wildcard/JIT ambiguity;
- freeze acceptance bank до hook behavior mutation;
- disposable worktree topology для P3 canary;
- полный DoR reconcile и `plan-lint`.

Ограничения: не исполнять P0; не коммитить; не менять packages,
`docs/reference.md`, `CHANGELOG.md`, FOREMAN или consumer repositories;
сохранить user-owned `tmp/` byte-for-byte.

## Design Pass 3/3 — 2026-07-24

Fresh finish обязан дополнительно:

- удалить любую P1.4 isolation через `HOME`/`CODEX_HOME`; использовать только
  task-specific temporary roots, переданные явными arguments/native flags;
- заменить динамический P4.1 `core modules/callers named by audit` точным
  списком `core/provider*.py` и `core/tests/test_provider*.py`;
- применить `package-contribution-protocol` к load-bearing shared/public
  changes: existing-seam survey, Rule of Three, alternatives, ADR и SemVer;
- дать каждому roadmap carrier одновременно semantic Next/model
  class/effort/capabilities/plan context и native Codex
  model/thinking/approval/sandbox/cwd/`NEW SESSION`;
- требовать `command.subagents` для каждого item carrier и fail closed без
  solo fallback, если capability не подтверждена;
- после finish передать план в отдельную fresh frontier/xhigh
  `audit-design`, а не начинать P0.

## Provider portability — 2026-07-24

Владелец уточнил, что план может исполняться Claude. Поэтому:

- `plans/<ID>/root/` — относительный canonical каталог long-lived
  plan-artifacts по plan-protocol, не OS `/root` и не путь для замены;
- canonical repo paths, contracts и semantic task commands должны читаться
  обоими providers; `.agents` и native launch blocks — projections;
- roadmap сохраняет обязательные local Codex recovery blocks, но добавляет
  детерминированный Claude/Codex renderer из
  `packages/task/configs/command-routing.json`;
- host-bound inputs допустимы только как явные evidence exceptions:
  user-owned `tmp/swissknifeman-audit.md`, `~/.codex` sessions и foreign
  journals. Claude на той же машине их читает; другой clone — нет;
- P0.1 fail-closed при отсутствии/hash drift и коммитит manifests,
  corpus/baseline в plan directory; только после этого P0.2+ не зависит от
  raw host paths. Cross-machine portability P0.1 заранее не заявляется.

## Owner portability decision — supersedes host-bound execution — 2026-07-24

Владелец потребовал вынести всё execution-required evidence в план до
`audit-design`. Поэтому:

- ни один item не зависит для исполнения от `tmp/`, `~/.codex`, foreign
  repositories, mAInd или другого hidden local state;
- в `artifacts/source-evidence/` материализуются full Perplexity audit
  snapshot, семь lossless journal snapshots, sanitized selected session
  incident evidence, manifests, precomputed corpus/baseline и stdlib verifier;
- raw rollouts целиком не копируются (сотни MB, secrets/reasoning risk);
  external paths остаются optional provenance и не участвуют в execution gate;
- P0.1 только проверяет и нормализует committed bundle. P0.2+ читают bundle
  artifacts; отсутствие внешнего origin не блокирует;
- Pass 3 finish и следующий `audit-design` возможны только после фактической
  materialization и deterministic verification bundle.

## Canonical self-contained planning — package capability — 2026-07-24

Владелец потребовал сделать подход не локальной особенностью этого плана, а
скомпилированным и тестируемым контрактом `plan-protocol`/`task-plan-design`:

- simple single-session/low-risk plan может ограничиться committed
  brief+acceptance;
- multi-session, high-risk, handoff и audit plans обязаны ссылаться только на
  committed execution inputs или exact paths, produced by a predecessor;
- host/chat/mAInd/`tmp`/foreign paths разрешены только как typed
  provenance/advisory, не как execution inputs;
- evidence bundle, когда он нужен, минимизирует данные, не содержит secrets,
  chain-of-thought или raw bulk и имеет deterministic manifest/verifier;
- semantic carrier остаётся provider-neutral; Claude/Codex — renderers;
- правило должно быть enforced в Task Contract, `plan-design` и `plan_lint`,
  покрыто conformance/eval cases и опубликовано в canonical docs. Prose-only
  инструкция без lint/compiler/tests не считается выполнением.

## Pass 3 reopen — generated closure and Codex identity ownership — 2026-07-24

Audit attempt 2 был остановлен до verdict: inspection доказал два execution
gap, поэтому audit cap не израсходован, P0 не начинался.

- P1.1 замораживает version-first ledger и exact generated-scope guard.
  Skiller получает отдельную canonical map package-API и publication-unit
  versions; unrelated bucket manifests обязаны оставаться byte-identical.
- P1.2/P1.3/P2.2/P2.3 выполняют только порядок
  version bump → full owning generator/tree/locks/marketplaces → read-only
  second check → exact diff-scope assertion. Один `(name,version)` не может
  обозначать разные bytes.
- P2.2 является единственным владельцем canonical plan-protocol/command
  изменения. P2.3 расширяет independently-green compiler через frozen policy
  hook, но не редактирует canonical commands/protocol второй раз.
- `codex plugin list --json` read-only preflight подтвердил enabled
  `core@0.4.0` и `task@0.3.0`. Поэтому executable resolution удаляет все
  шесть root core и шесть root task auto-discovered adapter directories;
  installed generated bundles authoritative, conditional suppression
  запрещён. P1.4 cold-installs repository marketplaces into explicit
  temporary roots and требует каждую из 12 identities ровно один раз.
- Remaining `.agents/skills` — unique bootstrap adapters. Cold recovery
  проверяет canonical package paths and repository marketplaces, а не
  возвращает дублирующий auto-discovery layer.
