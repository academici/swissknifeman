# Review of P7.5 (working tree) - round 1

Reviewer: grok/grok-4.7/500k/high, headless read-only session 01a12047-edca-7250-86d3-3fb90ab878d0 (contextWindowTokens 500000, reasoning_effort high, from the session record).
Executor verification: each finding was reproduced by the executor's own run (new failing tests / document text) before correction.

**Verdict: RED**

One confirmed finding. The six section texts, hashes, projections, fixtures, goldens, and the root first-turn budget match the design.

## Major — contract scope count contradicts the inventory this change wrote

`packages/harness/docs/reference/provider-instruction-contract.md:10`, `:29`, and `:60`, against the scope table at `:51–58`.

The scope table now lists eight scopes (`root`, `skiller`, `harness`, `maind`, `analyst`, `task`, `artifex`, `brain`). The same document still says the canon is the root and its five package scopes, and that scope IDs are exactly the six IDs in `Scopes`. Line 60 says a conforming catalog contains all and only these eight scope records. Before this diff the purpose, the identity row, and the table all said six. Adding `artifex` and `brain` and changing only the later sentence left the normative identity row on six.

Reproduction (exit 1):

```bash
python3 - << 'PY'
import pathlib, re, sys
p = pathlib.Path("packages/harness/docs/reference/provider-instruction-contract.md")
lines = p.read_text().splitlines()
text = "\n".join(lines)
for n in (10, 29, 60):
    print(f"{n}: {lines[n-1]}")
start = text.index("## Scopes")
end = text.index("## Semantic sections")
rows = re.findall(r"^\| `([a-z0-9-]+)` \|", text[start:end], re.M)
print("scope table:", ", ".join(rows), f"({len(rows)} rows, {len(rows)-1} packages)")
ident = [ln for ln in lines if "Scope IDs" in ln][0]
print("identity says six:", "six" in ident)
print("purpose says five packages:", "five package scopes" in lines[9])
print("scopes sentence says eight:", "eight scope records" in lines[59])
if "six" in ident and len(rows) != 6:
    sys.exit(1)
PY
```

```
10: its five package scopes. `CLAUDE.md` and `AGENTS.md` are independent provider projections of
29: | Scope IDs | exactly the six IDs in `Scopes` |
60: A conforming catalog contains all and only these eight scope records and all and only the two
scope table: root, skiller, harness, maind, analyst, task, artifex, brain (8 rows, 7 packages)
identity says six: True
purpose says five packages: True
scopes sentence says eight: True
```

Suggested fix: in that file, change "five package scopes" to "seven package scopes" and "exactly the six IDs" to "exactly the eight IDs".

## Checked, no finding

- Section prose in `packages/brain/common.md` matches the six design strings in order 1–6. Catalog `sha256` is `a6a588469f01304de1076e2c997a8801dd2c6c7d3e9ae3f076b68785593f9ed4`, the file hash. Every compatibility assertion is a substring of its section. Non-brain catalog scopes are unchanged. `catalog_version` is `1.5.0`.
- `harness instructions check` in sandbox `/tmp/skm-sandbox-rv3257077` (removed afterward): `OK — 32 targets`, all `clean/noop`, including the four `packages/brain` projections. `generate-provider-instructions.py --check` and `ecosystem-units.py check` exited 0.
- Lock diffs on existing records are only the catalog and contract source hashes, `source_hash`, and `catalog_version` in metadata. Rendered hashes of other scopes are unchanged. Golden digest changes are only `provider-instructions.md` and `instruction-literal-coverage-v1.json`. The CLI golden adds the four brain targets and `catalog_version` `1.5.0`. Existing golden targets are unchanged.
- Root first-turn budget: `Total: 2464 current — OK`. `git diff` is empty for `CLAUDE.md`, `AGENTS.md`, `.claude`, `.cursor/rules`, and `.grok/rules`. SessionStart hooks contribute 0. The measured root inputs did not change.
