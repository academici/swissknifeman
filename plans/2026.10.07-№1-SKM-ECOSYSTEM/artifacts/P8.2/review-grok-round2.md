**Verdict: GREEN**

The three round-1 defects are fixed, and the callers of the changed functions keep the same results for a library-only registry. `bash packages/skiller/scripts/test.sh` passed (832 tests).

## Checked, no finding

- **Sync name clash.** `skillset._select` (`skillset.py:242`) keeps a library entry ahead of a host entry in either bucket order. `do_sync` for `["lib-a", "env-skills"]` and `["env-skills", "lib-a"]`, including the default core set, wrote `SKILL.md` containing `FROM LIBRARY` and warned that the library copy is used. The include path and `_pull_requires` use that same choice. Selecting only `mod-a` with exclude `env-skills/sk-b` leaves `sk-a`.
- **Vendor and budget exclude.** `resolve_requires` (`vendor.py:102`) adds `<host bucket>` and `<host bucket>/<rel>` when `owners` is passed. `do_vendor` with `--exclude env-skills/sk-b` installs one skill and no `mod-b`, both for bucket `env-skills` and for `mod-a` alone (the requires path). `budget.resolve_active_set` passes the same owners (`budget.py:81`); `sk-b` is absent and `pulled` is empty. A call that omits `owners` still honors the bare name `sk-b`.
- **Status overlap.** `channel_overlap` (`status.py:35`) expands a host bucket on both sides only when `env` is passed and the registry has host buckets. `cmd_status` for enabled `env-skills` plus a vendored `mod-a` source printed `Included: env-skills keep` and `DOUBLE CHANNELS: buckets [mod-a]`. The reverse case, enabled `mod-b` against a vendored `skills/env-skills/...` path, printed `DOUBLE CHANNELS: buckets [mod-b]`. Enabled `env-skills` against vendored `lib-a` produced no overlap.
- **Library-only registries.** With no `provided_by: host`, `host_bucket_owners` is empty, `channel_overlap(..., env)` matches the plain intersection, and an excluded `code-style` is not pulled back (`test_unit`, `test_status`, `test_channel_parity`). The real `buckets.json` has no `provided_by`, and the real host file has no `bucket_aliases`. Module skills `brain` and `task` do not share a name with a library skill.
- **P8.1.** Not re-opened. The round-2 edits are not in that change.
