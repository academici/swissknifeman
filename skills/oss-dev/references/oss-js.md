---
name: oss-js
description: JS/TS-специфика для OSS-проектов: package.json, pnpm, tsconfig, vitest, ESM/CJS, npm publish, CI matrix
type: reference
parent: oss-development
---

# Reference: OSS JS/TS

Загружается дополнительно к `.ai/skills/oss-dev/oss-development.md` когда язык проекта — JavaScript или TypeScript (ThemeOn, npm-пакеты и подобные).

---

### package.json минимум

```json
{
  "name": "@scope/package-name",
  "version": "0.1.0",
  "description": "Одна строка",
  "type": "module",
  "main": "./dist/index.cjs",
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js",
      "require": "./dist/index.cjs"
    }
  },
  "files": ["dist", "README.md", "LICENSE"],
  "scripts": {
    "build": "tsup",
    "test": "vitest run",
    "lint": "eslint src",
    "typecheck": "tsc --noEmit",
    "prepublishOnly": "pnpm build && pnpm test"
  },
  "engines": { "node": ">=18" },
  "license": "MIT",
  "repository": { "type": "git", "url": "git+https://github.com/vendor/repo.git" },
  "keywords": [],
  "devDependencies": {
    "typescript": "^5.4.0",
    "vitest": "^1.5.0",
    "tsup": "^8.0.0",
    "eslint": "^9.0.0"
  }
}
```

### Package Manager

| Менеджер | Когда | Lockfile |
|:---|:---|:---|
| **pnpm** | По умолчанию для новых проектов (быстрее, эффективнее по диску) | `pnpm-lock.yaml` |
| npm | Если нужна максимальная совместимость / нет CI на pnpm | `package-lock.json` |
| yarn | Только если монорепа уже на yarn workspaces | `yarn.lock` |

Один lockfile в репо. Коммитить **обязательно**.

### tsconfig.json минимум (TypeScript)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "dist",
    "rootDir": "src",
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

### ESM / CJS Dual Publishing

Современный пакет публикует оба формата через `tsup` или `unbuild`:

```bash
# tsup конфиг
tsup src/index.ts --format esm,cjs --dts --clean
```

Поле `exports` в `package.json` критично — без него require/import может выбирать неправильный entry. `"type": "module"` означает что `.js` = ESM, `.cjs` = CommonJS.

### Static Analysis & Lint

```bash
# TypeScript — strict обязательно
pnpm typecheck

# ESLint 9 (flat config) или typescript-eslint
pnpm lint

# Prettier — отдельный шаг, не часть lint
pnpm prettier --check src
```

### Node Version Support Matrix

```
Node 18 LTS — minimum (Active LTS до апреля 2025)
Node 20 LTS — recommended (Active LTS до апреля 2026)
Node 22 LTS — latest

Правило: поддерживать только активные LTS-версии Node.
```

### Vitest структура

```
tests/
├── unit/           # Изолированные тесты
├── integration/    # С реальными зависимостями
└── e2e/            # Сквозные сценарии
```

```bash
pnpm vitest run --coverage
```

Coverage порог в `vitest.config.ts`:

```ts
test: {
  coverage: {
    provider: 'v8',
    thresholds: { lines: 80, functions: 80, branches: 75, statements: 80 }
  }
}
```

### npm Publishing

```bash
# 1. Логин (один раз)
npm login

# 2. Проверить что войдёт в пакет
npm pack --dry-run

# 3. Версия + тег
pnpm version patch  # или minor / major
git push --follow-tags

# 4. Публикация
npm publish --access public  # для @scope пакетов
```

Для автоматизации — GitHub Actions с `NPM_TOKEN` secret (см. `release-engineering` скилл).

### .github/workflows/ci.yml для JS/TS

```yaml
- Node versions: [18, 20, 22]
- OS: [ubuntu-latest, macos-latest, windows-latest] (если есть file IO)
- pnpm install --frozen-lockfile
- pnpm lint
- pnpm typecheck
- pnpm test -- --coverage
- pnpm build
```

---
