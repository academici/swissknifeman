# License

Skill reference `dx-design`.

MIT (or other, see oss-governance)
```

**What should NOT be in README:**
- Long story «how we came up with the idea»
- Comparisons with competitors (this is in a separate `COMPARISON.md`)
- Roadmap inside README (this is in `ROADMAP.md`)
- Full API reference (this is in docs)

### 3. API ergonomics
**Rules:**

| Rule | Example good | Example bad |
|:---|:---|:---|
| One main entry-point | `import { Brain } from 'brainkit'` | `import { BrainCore, BrainConfig, brainSetup } from 'brainkit/internal/...'` |
| Sensible defaults | `new Brain()` works | `new Brain({ config: required })` |
| Builder pattern for complex | `Brain.builder().withCache().build()` | `new Brain(c, t, e, x, t)` |
| Async-first, not sync wrappers | `await b.query()` | `b.queryAsync()` (name gives sync-legacy) |
| Error throws, not return-null | `throw new BrainError(...)` | `return null /* check it yourself */` |
| Type-safe (not `any`) | `Brain<TResponse>` | `query(): Promise<any>` |

**Test:** new user must write first useful integration **without reading API reference**. Only README + IntelliSense.

### 4. Error messages
**Structure of good error:**

```
[ProjectName] {What happened.}
  Why: {Why - a short explanation of the reason.}
  Fix: {What should the user do.}
  Docs: {link on raison-d'être this error or troubleshooting.}
```

Example good:
```
[Brain] Cannot connect to model endpoint.
  Why: BRAIN_API_KEY env var is missing.
  Fix: export BRAIN_API_KEY=sk-... and retry.
  Docs: https://brainkit.dev/docs/auth#api-key
```

Example bad: `Error: ECONNREFUSED 127.0.0.1:443`

**Rule:** each unique error must have URL in the documentation (even if it's an anchor in one troubleshooting-document).

### 5. CLI UX (if applicable)

| Rule | Example |
|:---|:---|
| `<name> --help` shows useful summary | not just a list of flags |
| `<name>` (without arguments) DOESN'T crash | shows hint or launches REPL |
| Colors only in TTY (NO_COLOR / not piped) | autodetection |
| Progress bar for > 2 sec operations | `███░░░ 42%` |
| `--json` flag for machine output | for scripts |
| Exit code 0 = ok, 1 = user error, 2 = bug | standard |

### 6. Documentation (structure)

Minimum for `v1.0+`:

```
docs/
├── README.md           # → links to sections below
├── getting-started.md  # 5-minute tutorial
├── core-concepts.md    # mental model of the package
├── api/                # generated API reference (TypeDoc / phpDocumentor / dartdoc)
├── guides/             # recipes under use cases
│   ├── caching.md
│   ├── streaming.md
│   └── ...
├── troubleshooting.md  # common problems (is synced with error messages)
└── migration/          # for each MAJOR — migration guide
    ├── 0-to-1.md
    └── 1-to-2.md
```

Documentation **next to the code** (in the repo), not on a separate site that is dying.

---
