---
name: oss-js
description: JS/TS-specifics for OSS-projects: package.json, pnpm, tsconfig, vitest, ESM/CJS, npm publish, CI matrix
type: reference
parent: oss-development
---

# Reference: OSS JS/TS

Loaded in addition to `.ai/skills/oss-dev/oss-development.md` when the project language is JavaScript or TypeScript (ThemeOn, npm-packages and similar).

---

### package.json minimum

```json
{
  "name": "@scope/package-name",
  "version": "0.1.0",
  "description": "One line",
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

| Manager | When | Lockfile |
|:---|:---|:---|
| **pnpm** | Default for new projects (faster, disk efficient) | `pnpm-lock.yaml` |
| npm | If you need maximum compatibility / no CI on pnpm | `package-lock.json` |
| yarn | Only if the monorep is already on yarn workspaces | `yarn.lock` |

One lockfile in the repo. Commit **required**.

### tsconfig.json minimum (TypeScript)

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

The modern package publishes both formats via `tsup` or `unbuild`:

```bash
# tsup config
tsup src/index.ts --format esm,cjs --dts --clean
```

Field `exports` in `package.json` critical - without it require/import may choose the wrong one entry. `"type": "module"` means that `.js` = ESM, `.cjs` = CommonJS.

### Static Analysis & Lint

```bash
# TypeScript — strict required
pnpm typecheck

# ESLint 9 (flat config) or typescript-eslint
pnpm lint

# Prettier — separate step, not part lint
pnpm prettier --check src
```

### Node Version Support Matrix

```
Node 18 LTS — minimum (Active LTS until April 2025)
Node 20 LTS — recommended (Active LTS until April 2026)
Node 22 LTS — latest

Rule: support only active LTS-versions Node.
```

### Vitest structure

```
tests/
├── unit/           # Isolated tests
├── integration/    # With real dependencies
└── e2e/            # End-to-end scenarios
```

```bash
pnpm vitest run --coverage
```

Coverage threshold in `vitest.config.ts`:

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
# 1. Login (once)
npm login

# 2. Check what is included in the package
npm pack --dry-run

# 3. Version + tag
pnpm version patch  # or minor / major
git push --follow-tags

# 4. Publication
npm publish --access public  # for @scope packages
```

For automation - GitHub Actions with `NPM_TOKEN` secret (see `release-engineering` skill).

### .github/workflows/ci.yml for JS/TS

```yaml
- Node versions: [18, 20, 22]
- OS: [ubuntu-latest, macos-latest, windows-latest] (if available file IO)
- pnpm install --frozen-lockfile
- pnpm lint
- pnpm typecheck
- pnpm test -- --coverage
- pnpm build
```

---
