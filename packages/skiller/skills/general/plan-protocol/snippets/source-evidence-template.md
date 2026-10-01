# Evidence bundle template - `committed-bundle`-tier

Resolve `<task-package-root>` from the configured Task runtime before copying a command; it is
the package directory containing `lib/task/`. Use the same provider runtime locator as the Task
command, never a consumer-local package copy or another provider's environment variable.

Executable form of bundle requirements (SSOT formulations - `plan-portability-v1.md`
§Bundle plan requirements; here is the QUOTE and structure,
not a rewrite). Needed by EVERY item whose `portability.tier == "committed-bundle"`
(multi-session/high-risk/handoff/audit work) and which carries committed evidence
input beyond the normal `Files`/`Required Reads`.

## Bundle directory layout

```
plans/<PLAN-ID>/artifacts/<Pn.m>/evidence/
├── manifest.json # required - exact list of bundle members
├── verify.py # required - verifier (existence is verified, not executed by predicate)
└── <files> # minified set, exactly what is listed in manifest.json
```

## `manifest.json` - required fields

```json
{
  "bundle_id": "<Pn.m>-<slug>",
  "files": [
    "<bundle-relative path 1>",
    "<bundle-relative path 2>"
  ],
  "privacy": {
    "minimized": true,
    "excluded_classes": ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]
  },
  "producer": "<command/script that produced the bundle - deterministically, without clock/randomness/network>"
}
```

- `files` — EXACT list of bundle members (relative to the bundle directory); `manifest.json`
  and `verify.py` themselves are NOT included in this list (excluded from the `task_contract.bundle_lint` reconciliation).
- `privacy.minimized` - `true`, only if the bundle carries EXACTLY what it actually was
  read for execution input; `excluded_classes` names what is deliberately left FOR
  board (not “nothing”, but a list: `raw-transcript-bodies` / `chain-of-thought` /
  `tool-payloads` / `secrets` - one of those that could actually get there).
- `producer` - the command with which the bundle is reproduced (deterministically, by the same run
  on the same tree, without clock/randomness/network - otherwise `content_hash`/manifest is not
  is reproduced by an independent auditor, exactly defect F3/F4 of audit P2).

## Verification command

```bash
PYTHONPATH="<task-package-root>/lib" python3 -c '
from task.task_contract import BUNDLE_INPUT_POLICY, bundle_lint
code = bundle_lint(
    "plans/<PLAN-ID>/artifacts/<Pn.m>/evidence",
    manifest_path="plans/<PLAN-ID>/artifacts/<Pn.m>/evidence/manifest.json",
    verifier_path="plans/<PLAN-ID>/artifacts/<Pn.m>/evidence/verify.py",
    policy=BUNDLE_INPUT_POLICY,
)
print(code or "allow")
'
```

Green - `allow`. Failure - `BUNDLE_ARTIFACT_MISSING` (manifest/verifier not found on
disk) or `BUNDLE_PRIVACY_MISMATCH` (actual set of files ≠ `manifest.json::files`,
OR signature byte scan found a content class listed in
`declared_privacy.excluded_classes` as excluded, - `bundle_lint` CALCULATES this by
actual bytes, rather than reading the declaration as given, D23/F2/F4). Both codes are real,
not structural: repaired by the bundle ITSELF (remove unnecessary things/add missing ones to manifest),
not by weakening the check.

## Prohibited content classes (list, not example)

- **Raw transcript-bodies** (`raw-transcript-bodies`) - full agent dialogues/logs as
  yes; instead of them - an extracted fact with a link to the source.
- **Chain-of-thought** - intermediate reasoning of the model; instead of them - the final solution
  and its rationale in 1–3 lines.
- **Tool-payloads** - raw tool responses (full JSON API calls, etc.); instead of
  them is the extracted value.
- **Secrets** - tokens/passwords/keys/PII in any form, even test/example, similar
  to real ones by signature.

## Full dependency closure

If the bundle file refers to an artifact outside the bundle (different path, different bundle) —
the reference is EITHER brought inside the bundle (complete closure), OR the bundle is not self-sufficient
and the cold session crashes on the second file (`plan-portability-v1.md` §Bundle requirements).

## One neutral semantic carrier

`portability.semantic_carrier` + `provider_renderers` - bundle carries ONE neutral
form; Claude/Codex renderings are projections, never a source of truth
(`task-contract-v1.md:187-200`, `context`-values - the same table as
`snippets/launch-block-template.md`).
