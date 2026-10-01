# Polyglot-monorepo: how it works platform-service

Multilingual monorepo guide/runtimes under one roof - `services/` (core),
`packages/js|php|flutter/` (SDK), `apps/` (demo/consumers), `infra/` (Docker/K8s). Pattern
occurs in externalized-platforms (for example Loqum) — when one product gives away SDK on
several languages around a common runtime-kernels (reference - `research/AUDIT-loqum-findings.md`
at the root of the repository).

## When are monorepos and when are separate repositories

**Monorepo justified**, if:
- SDK in different languages **are required** synchronously follow one protocol/contract (breaking
  change in the contract - obviously breaking for everyone SDK at once);
- is common CI, which should fail if PHP-SDK and Flutter-SDK went their separate ways;
- one command (or closely related commands) owns both the kernel and SDK.

**Separate repositories are better**, if:
- SDK are developed by different teams with different release rates and do not have to be synchronous;
- language ecosystems pull incompatible tuling (their runners CI, their release cycles) and monorepo
  adds only a synchronization overhead, without providing consistency guarantees;
- consumers SDK do not need atomic cross-language commits.

Default rule: **if contract/protocol — is general and changes in one PR** → monorepo.
If everyone SDK — independent product with its own roadmap → separate repositories + version pinning
for the contract (semver-dependency, not git submodule).

## Structure

```
<repo>/
├── services/
│   └── core/            # runtime-core (one language, source of truth behavior)
├── contracts/            # protocol/schema — SSOT for codegen (see below)
├── packages/
│   ├── js/               # SDK for Node/browser — codegen from contracts/
│   ├── php/              # SDK for PHP-consumers - codegen from contracts/
│   └── flutter/          # SDK for Dart/Flutter — codegen from contracts/
├── apps/                 # demo applications / reference consumers SDK
└── infra/                # Docker, K8s-manifests, CI-infrastructure
```

Core (`services/core`) does not have to be the only one - but if there are several cores, each has its own
subdirectory in `services/`, rather than mixing with SDK-in batches `packages/`.

## Dependency direction: straight down

```
contracts/  →  services/  →  packages/*  →  apps/
```

- **Contracts do not depend on anything** — is a leaf node of the dependency graph, pure description
  protocol (schema/IDL), without importing runtime code.
- **services/** depend only on `contracts/`.
- **packages/*** (SDK) depend on `contracts/` (via codegen) and, if necessary, from `services/`
  like reference-implementation - but not vice versa.
- **apps/** depend on `packages/*`, never the other way around.
- **Upward-import prohibited**: `contracts/` does not import from `services/`; `services/` not
  imports from `packages/`.
- **App→app import prohibited**: applications in `apps/` do not import each other directly - general
  code between them or already in `packages/`, or not general.

Directional violation is the most common source of cyclic dependencies in polyglot-monorepo
(see gotchas below); keep it visible in CI (lint import rules/dependencies per-package), and not
in documentation only.

## Protocol/contracts like SSOT + codegen

One source of truth for the shape of data and calls - `contracts/` (schema, IDL, OpenAPI/protobuf/analogue
depending on protocol). From it **is generated** code for each language-SDK, but not written
hands in parallel in three places:

- contracts change one PR → codegen regenerates client types for JS/PHP/Dart;
- manual drift (someone just corrected PHP-SDK) is not possible structurally - the generated code is not
  is edited manually (gate: generated files - read-only in the review, the diff is relevant only in
  `contracts/` and in codegen-config);
- CI is obliged to check the relevance codegen (regenerate + diff --exit-code), rather than trust that
  the developer started the generator before committing.

Without this rule SDK inevitably diverge: PHP-SDK will receive the new field first Flutter-SDK, and
bug reports will be «field is in one SDK and not in the other» — and not «protocol changed».

## Versioning: per-package (default), unified — only for narrow lockstep-cases

**Per-package semver — default** for polyglot-monorepo: each SDK (`packages/js`, `packages/php`,
`packages/flutter`) is independently versioned and published to its own registry (npm/Packagist/pub.dev) with
with its version number. Reasons:
- SDK in different languages are rarely released synchronously (y Flutter-there may not be a release breaking change,
  when PHP gets major);
- consumers of one SDK should not be upgraded due to a change in something else;
- is a standard for polyglot monorepo tooling (see Nx/Nrwl — independent packages with their own
  versioning as base mode, lockstep — optional over mode).

**Unified/lockstep-versioning** (all packages of the same version in one release) is only justified for
**narrow, monolingual** cases - when monorepo packages are closely related, always released together and
are intended for one circle of consumers (a typical example is a set of packages of one framework on
same language). For polyglot-platforms with different consumer languages lockstep creates a false
synchronicity: PHP-the consumer is forced to perceive "version bump", caused by a change only in
Flutter-SDK.

## Lockfiles: separate per manager, not shared

Each language pack has its own lockfile of your manager - do not try to combine them into a common one:

```
packages/js/package-lock.json     # npm/pnpm/yarn — yours lockfile
packages/php/composer.lock        # Composer — yours lockfile
packages/flutter/pubspec.lock     # pub — yours lockfile
```

Don't mix dependency resolution between ecosystems and don't take out one lockfile to root
monorepo covering all languages - managers of different ecosystems do not know how to read others lockfiles, and
attempt at unification gives either a non-working file or a false sense of version synchronization, which
actually no.

## CI: multi-lang

Matrix CI should reflect the real boundaries of dependencies, and not drive everything to each PR:

- **Path-based triggers**: change only in `packages/php/` is not required to drive Flutter-tests
  (and vice versa) — unless it's PR, touching `contracts/` (then they chase **all** SDK, because
  that the contract is general).
- **Individual job'language**: PHP job (composer install + PHPUnit), Node job (npm ci + vitest/jest),
  Flutter job (pub get + flutter test) — is not one universal container with all toolchains at once.
- **Codegen-check** — separate mandatory job: `regenerate contracts → git diff --exit-code`
  (catches the forgotten re-generate).
- **Build order** matches dependency direction: `contracts` codegen → `services` build/test →
  `packages/*` build/test (parallel between languages, since they do not depend on each other) → `apps`
  build/test.

## Gotchas

- **Cyclic imports** usually means a violation dependency direction (see above) — SDK,
  importing something from `apps/`, or `services/`, pull type from concrete SDK instead
  `contracts/`. Repaired by returning the duty to `contracts/`, and not a hack in the build graph.
- **Build order** — forgotten assembly `contracts/` before SDK gives outdated generated code,
  which compiles silently (types are valid, but not the same). Explicit step codegen before assembling each
  SDK, do not rely on cache.
- **False sense of synchronicity** from unified-versioning (see above) — delays unnecessary releases.
- **General lockfile-temptation** — don't give in: each language has its own resolver, its own lockfile.
- **One CI-job for everything** — build time flows linearly with the number of languages; confuse parallelism
  language job's with dependency parallelism (SDK can be built in parallel with each other, but
  not before `contracts`/`services`).
- **PR, touching only one SDK**, should not require review from people unfamiliar with this language -
  path-based CODEOWNERS reduces noise, but does not cancel the mandatory codegen-check on edits
  `contracts/`.

## Skiller-integration

For a project of this form (`services/` + `packages/js|php|flutter/` + `apps/` + `infra/`) in skiller
already exists **project_type `platform-service`** ([profile](https://github.com/academici/swissknifeman/blob/main/packages/skiller/profiles/platform-service.json)) —
includes buckets `architect, ai, oss-dev, general, php, php-packages, frontend, frontend-vue,
frontend-backend, devops` + MCP `context7`. Usage:

```bash
skiller connect --profile platform-service
skiller vendor --profile platform-service
```

Clustered **preset `polyglot-node-php-flutter`** (end-to-end set of skills for this combination of languages
over the profile, by find [#3 integration audit Loqum](https://github.com/academici/swissknifeman/blob/main/research/AUDIT-loqum-findings.md))
at the time of writing this guide **not created yet** — is listed in the backlog along with the find
[#1](https://github.com/academici/swissknifeman/blob/main/research/AUDIT-loqum-findings.md), which is already closed by the profile `platform-service` above. Before the preset appears
override profile buckets point by point `buckets`/`exclude` in `.swissknife.json` /
`.swissknifeman/config.json` (see [Profiles and auto-detection](./profiles) and [Checklist
integration](./integration-checklist)).

## See also
- [Profiles and auto-detection](./profiles) — how it works `project_type` → `buckets`.
- [Integration checklist](./integration-checklist) — wizard `skiller integrate` and manual steps.
- [Skills architecture](./skills-architecture) — CORE-policy, two channels, two configs.
