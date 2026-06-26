---
name: dependency-audit
bucket: oss-dev
version: 0.2.0
description: Аудит зависимостей: lockfile sanity, vuln scan, лицензионная совместимость, supply-chain risk, SBOM
risk: draft
persona: oss-dev
tags: [oss, compliance, security, dependencies, php]
requires: [oss-development]
produces_for: [security-design, release-engineering]
outputs: ["ProjectName/Dependency_Audit.md", "ProjectName/SBOM.json"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Dependency Audit

Применять когда: **перед первой публикацией** OSS-пакета, **перед MAJOR-релизом**, или **по триггеру** — security advisory, license question от потенциального enterprise-потребителя, supply-chain alert.

Должен быть **выполнен после `oss-development`** (есть `package.json` / `composer.json` / `pubspec.yaml`). Производит вход для `security-design` (compliance-pipeline) и для `release-engineering` (SBOM в release artefact).

---

## Когда НЕ применять

- Pet-project без зависимостей или с 1–2 stdlib зависимостями — overkill.
- Только что прогнали аудит < 7 дней назад и lockfile не менялся — переиспользовать предыдущий отчёт.
- Закрытый пакет без публикации — упрощённая проверка, не полный audit.

---

## 5 измерений аудита

5 измерений аудита зависимостей (vuln-scan, лицензии, supply-chain, freshness, SBOM) подробно — [references/audit-dimensions.md](references/audit-dimensions.md).

## Что агент добавляет сам

- **Renovate / Dependabot конфиг.** Без bot-driven updates аудит застаёт устаревший lockfile. Минимум: `.github/dependabot.yml` с group для minor/patch updates.
- **Provenance.** npm `--provenance` (через GitHub OIDC) — выходит за рамки audit, но завязан на CI release pipeline. Упомянуть в отчёте.
- **Reproducible builds.** Lockfile + frozen install (`npm ci` / `composer install --no-dev --prefer-dist --no-progress`) — для verifiable artefacts.
- **License-of-licenses.** Проверять не только direct deps, но и **транзитивные** — типичная утечка GPL.
- **Версионная политика обновлений.** Auto-merge для patches от trusted maintainers ОК; для majors — ручной review.

---

## Структура output-файлов

### `ProjectName/Dependency_Audit.md`

```markdown
---
project: [ProjectName]
audit_date: YYYY-MM-DD
audit_scope: production | production + dev
tooling: npm@X, composer@Y, ...
---

# Dependency Audit — [ProjectName]

## Сводка
- Direct deps: N
- Transitive deps: M
- Lockfile committed: yes/no
- License conflicts: 0
- Open vulnerabilities: 0 critical / 0 high / X moderate / Y low

## Lockfile
- Status: clean / dirty
- Phantom deps: ...
- Duplicates: ...

## Vulnerabilities
| Severity | Package | Version | Advisory | Status (fixed / accepted / blocked) |
|:---|:---|:---|:---|:---|
| ...     | ...     | ...     | GHSA-XXX | fixed in 1.2.4 |

## License inventory
| License | Count | Packages |
|:---|:---|:---|
| MIT | 142 | ... |
| Apache-2.0 | 12 | ... |
| ISC | 8 | ... |

**Conflicts / red flags:** [список или «нет»]

## Supply-chain risk
- Bus-factor red flags: ...
- Recent ownership changes: ...
- Postinstall scripts allowlist: ...

## SBOM
→ `ProjectName/SBOM.json` (CycloneDX 1.5)

## Action items
- [ ] ...
- [ ] ...

## Next audit
- Триггер: следующий MAJOR / security advisory / 90 дней (что раньше)
```

### `ProjectName/SBOM.json`
Сгенерированный файл, не редактируется вручную. Регенерируется при каждом релизе.

---

## Ссылки

- [references/composer.md](references/composer.md) — composer-специфика:
  команды по измерениям, roave/security-advisories, reproducible installs,
  composer-грабли, SBOM для PHP.
- `oss-dev/oss-development` — предпосылка: даёт манифест (`composer.json`/`package.json`), по которому идёт аудит.
- `oss-dev/release-engineering` — потребитель: SBOM публикуется как release artefact.
- `oss-dev/oss-governance` — LICENSE-выбор проекта; лицензионная совместимость зависимостей — здесь.
- `architect/security-design` — потребитель: vuln/supply-chain находки идут в compliance-pipeline.
- `php-packages/laravel-package-compatibility` — composer-constraints, версии PHP/Laravel/Testbench для PHP-пакетов.
- `php/static-analysis` — Pint/PHPStan/Rector: качество кода рядом с аудитом зависимостей.

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Релиз `v1.0+` без audit-отчёта
- Игнорировать `critical`/`high` уязвимости
- Принимать в зависимости GPL/AGPL/BUSL пакеты без явного обоснования и approval
- Использовать пакет без явной SPDX-лицензии
- Допускать postinstall-скрипты от untrusted мейнтейнеров без allowlist
- Не коммитить lockfile в приложении (для библиотек — см. дискуссию выше)
- Полагаться на `npm audit` как единственный инструмент — он не ловит supply-chain
