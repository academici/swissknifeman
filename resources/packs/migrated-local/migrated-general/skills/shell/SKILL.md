---
name: shell
description: "Growing cookbook of shell constructs compatible with this environment's hooks (currently rm/rmdir vs the safe-dirs auto-approve hook; more patterns get added over time). Activate on a hard-deny-hook block and before writing rm/rmdir commands."
---

# Shell (compatibility with environment hooks)

A single growing skill on writing shell commands so this environment's hooks
let them through instead of blocking them. Currently one section — `rm`/`rmdir`
vs the `safe-dirs` `auto-approve` hook; as new patterns (other commands, other
hooks) are found, add new sections here — don't spin up a separate skill per
pattern.

## rm/rmdir vs safe-dirs auto-approve

### When to activate

- You hit `Blocked: dangerous operation (deny_hard). Execute manually when
  necessary. rm in trusted folders you can allow: harness safe-dirs` —
  BEFORE retrying the same command.
- Before writing ANY `rm`/`rmdir` command inside a trusted tree (`~/projects`,
  `~/Vaults`, registered projects — see `safe-dirs.json`).
- Before wrapping `rm`/`rmdir` in `for`/`while`/`if`/`case`, `xargs`, `sudo`,
  `env VAR=x`, or calling them from a function/alias.

### Why

The `~/.claude/hooks/auto-approve` hook asks `lib/safedirs.py` for a verdict
before `deny_hard`: a command is safe only if EVERY `rm`/`rmdir` occurrence
validates against the trusted-dirs allowlist (`safe-dirs.json` — a
MACHINE-OWNED config at the monorepo root; project-level
`.claude/auto-approve.config.json` cannot see or override it — otherwise a
hostile repo could grant itself `rm`).

**Key analyzer limitation (self-documented): "don't emulate the shell — reject
what isn't understood."** The tokenizer splits a command into segments ONLY on
punctuation `;|&<>()` — keywords `for`/`do`/`done`/`if`/`then`/`else` do not
start a new segment. As a result `rm`/`rmdir` inside `for ... do rm ... done`
can never be the "first token of its segment" — the exact same rule that
catches `sudo rm`/`xargs rm`/`FOO=x rm` (heuristic: "rm not at segment head →
unsafe, something may precede it"). Consequence: **a loop containing
`rm`/`rmdir` ALWAYS gets `deny_hard`, even if the paths are inside the
allowlist** — containment checking is never reached.

### Algorithm

1. **`rm`/`rmdir` must be the FIRST token of its segment.** A segment is the
   chunk between `;`/`|`/`&`/`&&`/`||`/`(`/`)`. The only allowed exception is
   `git rm` (masked separately, `j==1` when `toks[0]=="git"`).
   - ❌ `for f in a b c; do rm -rf "$f"; done` — `rm` is second token, after `do`.
   - ❌ `sudo rm -rf x`, `xargs rm -rf`, `FOO=1 rm -rf x` — same rule.
   - ✅ `rm -rf a b c` — one call, multiple paths as arguments.
   - ✅ five separate `rm -rf <path>` calls (one Bash tool call per path) if
     they truly can't be merged into one command.
2. **Flags — strict whitelist.** `rm`: short `-r -R -f -v -d -i -I` (any
   combination) or long `--recursive --force --verbose --dir`. `rmdir`: `-v`
   or `--verbose --ignore-fail-on-non-empty`. `rmdir --parents`/`-p` is
   FORBIDDEN (reaches into parent dirs). Any other flag → unsafe.
3. **Paths — no obfuscation.** `$`, `` ` ``, `{`, `}` in a path are forbidden
   (the character itself is unsafe, not just its expansion); a `..` path
   component is forbidden (lexically, before `realpath`); bare `~`/`~user` is
   not expanded (only `~/subpath` — from `$HOME`).
4. **Containment — realpath inside the allowlist.** The path (after
   `realpath`, tracking cwd for relative paths — including re-`cd` inside
   `&&` chains) must sit STRICTLY inside one of the `roots`
   (`safe-dirs.json`), must not be the root itself (except children via a
   `root/*` glob), must not cross `excludes`, must not touch a `.git`
   component (`protect_git`).
5. **Globs — allowed if they don't touch `.git`.** `rm -rf path/*` is allowed
   (children of `path`, not `path` itself), but a literal `.git` or a
   dot-glob (`.git*`, `.*`) in any pattern component is unsafe.
6. **If a legitimate `rm` still gets blocked** — do NOT retry the same command
   (anti-pattern). First rewrite it per rule 1 (no loop/wrapper, multi-arg or
   separate calls). If a loop/dynamic path list is SEMANTICALLY required (not
   rewritable as multi-arg) — use the `harness safe-dirs delete` escape hatch
   (below), not a repeated `rm`. If that's unavailable either — ask the user
   to run it manually (`!`-prefixed command).
7. **Multi-line commands (`\n`/`\r` in the body) are always unsafe**
   (segmentation is unreliable). Keep `rm`/`rmdir` commands single-line.

### Escape hatch: `harness safe-dirs delete` (bypasses shell rm/rmdir)

When a legitimate deletion SEMANTICALLY can't be rewritten as multi-arg `rm`
(dynamic path list, a loop is required) — use:

```
harness safe-dirs delete <path> [<path> …] [--dry-run]
```

- **Doesn't go through shell `rm`/`rmdir` at all** — `deny_hard` matches the
  words `rm`/`rmdir`/`sudo`/… as a substring ANYWHERE in the command
  (`config.deny_hard`); `harness safe-dirs delete ...` contains none of them,
  so the hook doesn't block it on input. That's why the subcommand is named
  `delete`, not `rm`.
- **Not a second source of truth.** Internally reuses the SAME containment
  code as the hook (`_hook_module` loads
  `configs/.../auto-approve/lib/safedirs.py` directly) — same allowlist, same
  `.git` guard, same "what's safe" semantics, no reimplementation.
- **Deletion only, concrete paths only.** No globs/wildcards (`*`, `?`, `[`,
  `$`, `` ` ``, `{`, `}`) and no arbitrary exec — this is not a Swiss-army-knife
  wrapper, just one narrow escape hatch (security lesson: a generic "run
  anything, I'll decide what's safe" helper becomes a hole past `deny_hard`
  itself).
- `--dry-run` prints what would be deleted without touching anything.
- Every deletion (dry-run and real) is appended to a JSONL audit log
  `~/.claude/logs/safe-delete-decisions.jsonl` (not controlled by the target).
- A path outside the allowlist / a `.git` component / a `..` component / a
  glob character → an explicit refusal (`die`), never a silent no-op.

### Growing cookbook: blocked vs safe

Concrete construct table — `snippets/blocked-vs-safe.md`. Append a row when you
hit a new parser anti-pattern; don't rewrite the SKILL body — the cookbook is
kept in a snippet on purpose so it can grow without bloating the skill.

### Checklist

- [ ] `rm`/`rmdir` is the first token of its segment (no `for/if/sudo/xargs/env=` before it).
- [ ] Flags only from the whitelist (no `-p`/`--parents` on `rmdir`).
- [ ] Paths contain no `$`/`` ` ``/`{`/`}`/`..` component.
- [ ] Path(s) sit under a known trusted root (`safe-dirs.json`), don't cross
      an `exclude`, don't touch `.git`.
- [ ] Single-line command (no `\n`/`\r` inside).
- [ ] If blocked — don't retry the same command: rewrite the form first
      (multi-arg/separate calls), use `harness safe-dirs delete` if a loop is
      semantically required, otherwise ask the user to run it manually.

## Related skills

`anti-drift` (discipline: don't blindly repeat the same action).
