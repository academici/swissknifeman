# Blocked vs safe (cookbook, is complemented)

Growing table of specific `rm`/`rmdir`-structures encountered
`safe-dirs`-hook. A new pattern has been found - add the line, don’t rewrite it
body `SKILL.md`.

| Pattern | Verdict | Why | Replacement |
|:--|:--|:--|:--|
| `for f in a b c; do rm -rf "$f"; done` | ❌ deny_hard | `rm` is not the first segment token (`do rm ...`) | `rm -rf a b c` (one call) |
| `sudo rm -rf x` | ❌ deny_hard | `rm` not the first token (`sudo rm`) | run manually (`!`-prefix) |
| `find . -name '*.tmp' -exec rm {} \;` | ❌ deny_hard | `rm` inside `-exec`, is not a segment head | `find . -name '*.tmp' -delete` (not rm) or manual confirmation |
| `xargs rm -rf` | ❌ deny_hard | `rm` not the first token (`xargs rm`) | separate calls `rm -rf <path>` |
| `rmdir -p a/b/c` | ❌ deny_hard | `-p`/`--parents` not whitelisted (climbs into parents) | `rmdir a/b/c` without `-p`, or `rm -rf a` |
| `rm -rf a b c` (all under trusted root) | ✅ safe | `rm` — segment head, flags/paths are valid | — |
| `rm -rf path/*` (does not touch `.git`) | ✅ safe | glob - children of the root, not the root itself, not `.git` | — |
| `rm -rf .git/hooks/*` | ❌ deny_hard | `protect_git`: component `.git` on the way | manual confirmation |
| 5 separate Bash-calls `rm -rf <path>` | ✅ safe | each - its own secure segment | — |
| for-loop with a dynamic list of paths, semantically is not rewritten to multi-arg | ❌ deny_hard (in form, not in essence) | loop always triggers `rm`/`rmdir` out of my head | `harness safe-dirs delete <path> [<path> …]` (does not pass through shell rm in general) |
