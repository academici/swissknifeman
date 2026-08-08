---
name: dart-package-development
bucket: dart
version: 0.1.0
description: "Use when developing, maintaining, or releasing a Dart package/SDK: pubspec, public API, null safety, tests, and compatibility. Not for Figma-based Flutter screens."
risk: read
persona: oss-dev
tags: [dart, pub, package, sdk, api, null-safety, testing, compatibility]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Dart package development

Use this skill for Dart libraries and SDKs: public contract, package layout,
compatibility, and verifiability. It does not replace `mobile/figma-to-flutter`
for Flutter interfaces and does not impose Flutter, state management, or FFI
on a package without those dependencies.

## When to activate

- creating or changing a Dart package, library, or SDK;
- changing public types, exports, the async contract, serialization, or package version;
- preparing a release or checking backward compatibility of a Dart API.

Do not activate it for implementing a Flutter screen from Figma; use
`mobile/figma-to-flutter` instead.

## Inputs

- `pubspec.yaml` and its supported SDK constraint;
- existing public entrypoint files under `lib/`, tests, and CI commands;
- the requested change and the consumer's expected contract.

## Algorithm

1. Read `pubspec.yaml` first: name, SDK constraint, runtime/dev dependencies, and
   available scripts. Do not change a constraint or dependency version without a task for it.
2. Separate public surface from implementation: consumers receive stable entrypoint exports
   from `lib/`; internal details must not become an accidental contract. Before changing,
   list the affected public types, methods, enum values, errors, and payloads.
3. Preserve the type and async contract: do not turn sync API into async or the reverse without
   an explicit migration; do not conceal a nullable/non-nullable change; new errors and fields
   must remain compatible with expected consumer behavior.
4. For models on a network/file boundary, check both directions: a correct payload encodes as
   expected, valid input decodes, and invalid input gives controlled diagnostics. Fix a
   cross-language contract with shared fixtures, not manually duplicated tests.
5. Add or update tests for changed observable behavior. Use the project's actual commands;
   the usual minimum is `dart analyze`, `dart format --output=none --set-exit-if-changed .`,
   and `dart test`. Do not report green if a command was not run or is unavailable.
6. Before release, separate compatible from breaking change; change the version only inside a
   release task and check that changelog/migration notes cover the public-contract change.

## Quality checklist

- [ ] Public exports and affected API are listed before implementation.
- [ ] Null safety, sync/async behavior, and errors do not change implicitly.
- [ ] Changed observable behavior has a test.
- [ ] Data boundaries have an encode/decode or conformance-fixture check.
- [ ] `dart analyze`, format check, and tests ran or are honestly marked unavailable.
- [ ] Version and migration/changelog changed only for release or breaking scope.

<!-- ru-source-sha256: 953d33e949f23fc6f314a600ba409ec3e882e2dcd923b29f84530c2dd2292af5 -->
