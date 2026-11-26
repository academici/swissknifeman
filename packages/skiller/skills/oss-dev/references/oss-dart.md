---
name: oss-dart
description: Dart/Flutter-specifics for OSS-projects: pubspec.yaml, pub.dev, melos, flutter compat, dart test, CI matrix
type: reference
parent: oss-development
---

# Reference: OSS Dart/Flutter

Loaded in addition to `.ai/skills/oss-dev/oss-development.md` when the project language is Dart (pure Dart packages or Flutter-plugins).

---

### pubspec.yaml minimum

```yaml
name: package_name
description: One line (60-180 characters - otherwise pub.dev fines score)
version: 0.1.0
homepage: https://github.com/vendor/repo
repository: https://github.com/vendor/repo
issue_tracker: https://github.com/vendor/repo/issues

environment:
  sdk: ">=3.3.0 <4.0.0"
  flutter: ">=3.19.0"   # only for Flutter-plugins

dependencies:
  meta: ^1.12.0

dev_dependencies:
  test: ^1.25.0
  lints: ^3.0.0
  mocktail: ^1.0.0

# For Flutter-plugin additionally:
flutter:
  plugin:
    platforms:
      android:
        package: com.example.package_name
        pluginClass: PackageNamePlugin
      ios:
        pluginClass: PackageNamePlugin
```

**Naming convention:** package name - strictly `snake_case`, Latin, without numbers at the beginning. On pub.dev unique globally.

### Pub.dev Score (important for adoption)

pub.dev rates the package in 4 categories (max 160 points):

| Category | What is being checked |
|:---|:---|
| **Follow Dart conventions** | `dart analyze` without warnings, `dart format` clean |
| **Provide documentation** | README, dartdoc on public API ≥ 20%, CHANGELOG, example/ |
| **Platform support** | Platform support is declared correctly |
| **Pass static analysis** | 0 issues by lints + null-safety |

Target score: **140+ out of 160**.

### Static Analysis & Lint

```bash
# Analysis (uses analysis_options.yaml)
dart analyze

# Formatting (required for score)
dart format --set-exit-if-changed .

# For Flutter
flutter analyze
```

`analysis_options.yaml` minimum:

```yaml
include: package:lints/recommended.yaml  # for Dart
# or: package:flutter_lints/flutter.yaml for Flutter

analyzer:
  language:
    strict-casts: true
    strict-inference: true
    strict-raw-types: true

linter:
  rules:
    - prefer_const_constructors
    - prefer_final_locals
    - avoid_print
    - require_trailing_commas
```

### Dart/Flutter Version Support Matrix

```
Dart 3.0 — minimum (records, patterns, class modifiers)
Dart 3.3 — recommended
Dart 3.4+ — latest

Flutter 3.19 — minimum (Dart 3.3)
Flutter 3.22 — recommended
Flutter 3.24+ — latest

Rule: support last stable + previous stable.
```

### Test structure

```
test/
├── unit/           # Pure logic
├── widget/         # Flutter widget tests (only Flutter)
└── integration/    # Integration test (only Flutter, with device)
```

```bash
# Dart package
dart test --coverage=coverage
dart pub global activate coverage
format_coverage --lcov --in=coverage --out=coverage/lcov.info

# Flutter package
flutter test --coverage
```

Coverage threshold ≥ 80% (same standard as in `oss-development`).

### Melos for monorepo

If there are several Dart-packages (`packages/foo`, `packages/bar`):

```bash
# Installation
dart pub global activate melos

# Bootstrap (link local deps)
melos bootstrap

# Run script on all packages
melos run test
melos run analyze
```

`melos.yaml` stores common scripts and versions. One lockfile per package.

### pub.dev Publishing

```bash
# 1. Dry-run — check before publication
dart pub publish --dry-run

# 2. Actual publication (requires Google account)
dart pub publish

# 3. For Flutter — via flutter:
flutter pub publish --dry-run
flutter pub publish
```

**Verified publisher:** configure the domain via DNS TXT-entry on pub.dev — increases confidence in the package.

### .github/workflows/ci.yml for Dart/Flutter

**Pure Dart:**
```yaml
- Dart versions: [stable, beta]
- dart pub get
- dart analyze --fatal-infos
- dart format --set-exit-if-changed .
- dart test --coverage=coverage
```

**Flutter:**
```yaml
- Flutter versions: [stable, beta]
- flutter pub get
- flutter analyze
- dart format --set-exit-if-changed .
- flutter test --coverage
- (for the plugin) flutter build for each platform
```

### Platform-specific for Flutter-plugins

The plugin must explicitly declare platforms in `pubspec.yaml`. Each platform = separate directory:

```
android/  # Kotlin/Java
ios/      # Swift/Objective-C
macos/    # Swift
linux/    # C++
windows/  # C++
web/      # Dart only
```

Do not declare a platform if it is not actually implemented - pub.dev will reduce score for false advertising.

---
