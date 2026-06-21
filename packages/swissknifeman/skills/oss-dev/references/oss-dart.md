---
name: oss-dart
description: Dart/Flutter-специфика для OSS-проектов: pubspec.yaml, pub.dev, melos, flutter compat, dart test, CI matrix
type: reference
parent: oss-development
---

# Reference: OSS Dart/Flutter

Загружается дополнительно к `.ai/skills/oss-dev/oss-development.md` когда язык проекта — Dart (pure Dart пакеты или Flutter-плагины).

---

### pubspec.yaml минимум

```yaml
name: package_name
description: Одна строка (60-180 символов — иначе pub.dev штрафует score)
version: 0.1.0
homepage: https://github.com/vendor/repo
repository: https://github.com/vendor/repo
issue_tracker: https://github.com/vendor/repo/issues

environment:
  sdk: ">=3.3.0 <4.0.0"
  flutter: ">=3.19.0"   # только для Flutter-плагинов

dependencies:
  meta: ^1.12.0

dev_dependencies:
  test: ^1.25.0
  lints: ^3.0.0
  mocktail: ^1.0.0

# Для Flutter-плагина дополнительно:
flutter:
  plugin:
    platforms:
      android:
        package: com.example.package_name
        pluginClass: PackageNamePlugin
      ios:
        pluginClass: PackageNamePlugin
```

**Naming convention:** имя пакета — строго `snake_case`, латиница, без цифр в начале. На pub.dev уникально глобально.

### Pub.dev Score (важно для adoption)

pub.dev оценивает пакет по 4 категориям (макс 160 баллов):

| Категория | Что проверяется |
|:---|:---|
| **Follow Dart conventions** | `dart analyze` без warnings, `dart format` clean |
| **Provide documentation** | README, dartdoc на public API ≥ 20%, CHANGELOG, example/ |
| **Platform support** | Поддержка платформ заявлена корректно |
| **Pass static analysis** | 0 issues по lints + null-safety |

Целевой score: **140+ из 160**.

### Static Analysis & Lint

```bash
# Анализ (использует analysis_options.yaml)
dart analyze

# Форматирование (обязательно для score)
dart format --set-exit-if-changed .

# Для Flutter
flutter analyze
```

`analysis_options.yaml` минимум:

```yaml
include: package:lints/recommended.yaml  # для Dart
# или: package:flutter_lints/flutter.yaml для Flutter

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

Правило: поддерживать последний stable + предыдущий stable.
```

### Тесты структура

```
test/
├── unit/           # Чистая логика
├── widget/         # Flutter widget tests (только Flutter)
└── integration/    # Integration test (только Flutter, с устройством)
```

```bash
# Dart пакет
dart test --coverage=coverage
dart pub global activate coverage
format_coverage --lcov --in=coverage --out=coverage/lcov.info

# Flutter пакет
flutter test --coverage
```

Coverage порог ≥ 80% (тот же стандарт, что и в `oss-development`).

### Melos для монорепо

Если в репозитории несколько Dart-пакетов (`packages/foo`, `packages/bar`):

```bash
# Установка
dart pub global activate melos

# Bootstrap (link локальных deps)
melos bootstrap

# Запуск скрипта на всех пакетах
melos run test
melos run analyze
```

`melos.yaml` хранит общие скрипты и версии. Один lockfile per пакет.

### pub.dev Publishing

```bash
# 1. Dry-run — проверка перед публикацией
dart pub publish --dry-run

# 2. Реальная публикация (требует Google аккаунт)
dart pub publish

# 3. Для Flutter — через flutter:
flutter pub publish --dry-run
flutter pub publish
```

**Verified publisher:** настроить домен через DNS TXT-запись на pub.dev — повышает доверие к пакету.

### .github/workflows/ci.yml для Dart/Flutter

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
- (для плагина) flutter build для каждой платформы
```

### Платформ-специфика для Flutter-плагинов

Плагин должен явно объявлять платформы в `pubspec.yaml`. Каждая платформа = отдельная директория:

```
android/  # Kotlin/Java
ios/      # Swift/Objective-C
macos/    # Swift
linux/    # C++
windows/  # C++
web/      # Dart only
```

Не объявлять платформу, если она реально не реализована — pub.dev снизит score за false advertising.

---
