# Vendor skills: trust, audit, triage

About page **trust procedure** to external skills, and not about synchronization mechanics.
Mechanics - [Upstream-sync](./upstream-sync.md); distributing physical copies to the project -
[Skills from packages](./vendor-skills.md).

## Carrying rule

::: danger no findings ≠ safe
Triage stage `update-upstreams.sh --check` — **pattern scan, not trust boundary**.
An empty result does not mean that the bundle is safe.

- First-Party Skill Scanner Anthropic **does not supply**; her instructions -
  «thoroughly audit it before use», that is **human reading of all bundle files**
  ([Anthropic Engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)).
- CSA according to Trail of Bits (2026-06) bypassed ClawHub, Cisco and skills.sh simple techniques -
  whitespace inflation, precompiled bytecode hiding, archive indirection, prompt-style social
  engineering for LLM-steps; conclusion verbatim **«Don't outsource trust to a scanner»**
  ([CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-skill-scanner-bypass-20260610-csa/)).

Hence the design: **human audit - boundary, triage - repeat pass accelerator.**
Phrase «scan is green, it means it’s safe» is not allowed in reports and commits.
:::

## What it does `--check`

Two independent things, each with its own exit code:

| What | Event | Exit code |
|:--|:--|--:|
| Integrity verification | upstream/local copy out of print | `10` |
| **Content triage** | a suspicious pattern was found in the bundle files | **`11`** |
| Network failure | at least one file was not downloaded | `2` |
| Everything is clear | — | `0` |

Codes **intentionally not merged**: «upstream has changed» and «in the bundle there is a suspicious pattern» — different
events, and the operator is required to distinguish between them. The code is one scalar, so the higher one cancels the lower one
(`2 > 10 > 11 > 0`); full picture **always** is in `--json` (keys `triage`,
`stale_verdicts`, `triage_disclaimer`).

```bash
# person
bash scripts/update-upstreams.sh --check

# machine (JSON in stdout, human report in stderr)
bash scripts/update-upstreams.sh --check --json | python3 -m json.tool
```

## Four threat classes

The rules are stdlib-regular, one or two per class; each carries a comment in the code «what
class catches». A rule without a named class is not added to the set.

| Class | Rules | What we are looking for |
|:--|:--|:--|
| **prompt injection** | `INJ_IGNORE`, `INJ_DISREGARD`, `INJ_HIDE_FROM_USER`, `INJ_ROLE_OVERRIDE`, `INJ_INVISIBLE_CHAR` | interception instruction in prose/comments/fense, role substitution, invisible characters |
| **data exfiltration** | `EXF_SUSPECT_HOST`, `EXF_CRED_TO_NET`, `EXF_ENV_DUMP` | ephemeral receivers (`webhook.site`, ngrok, pastebin), reading secret along with network call, dump env |
| **malicious code execution** | `EXE_PIPE_TO_SHELL`, `EXE_B64_EXEC`, `EXE_OBFUSC_BLOB` | `curl … \| bash`, execution base64, long base64-blobs |
| **over-permissive tool use** | `PRM_TOOL_WILDCARD`, `PRM_PERMISSION_BYPASS`, `PRM_REMOTE_INSTRUCTIONS` | wildcard in `allowed-tools`, permission bypass, **instructions pulled from the network** |

Plus `BIN_UNREADABLE`: file not read as UTF-8, gets into lost and found - «could not
read» and «clean» are not the same thing.

**What is not and will not be in the stage.** YARA — external dependency (disabled
`root.engineering-invariants`). LLM-as-judge — is directly named CSA bypassed via social
engineering. IOC-sheets - public list exactly by Agent Skills does not exist, declare
«IOC-scan» without a list would be self-deception.

## Verdict carrier: block `audit` in `upstream.json`

A person's verdict is not a line in a report, but **machine readable entry next to the bundle**:
the plan file is mortal, the skill is distributed further. The block is additive, lies in `upstream.json`:

```json
"audit": {
  "verdict": "clean",
  "at": "2026-08-01",
  "by": "",
  "upstream_sha": "bb30f388386f647ddfd3e8e7cf8c69826ac59bbefe6b11403e5a498c09f1d2d7",
  "note": "is required when attention/risk — what exactly, in one line"
}
```

| Field | What does it mean | Gate `validate.sh` |
|:--|:--|:--|
| `verdict` | `clean` · `attention` · `risk` | out enum → ERROR |
| `at` | bundle READ date (is not the date the file was edited) | not `YYYY-MM-DD` → ERROR |
| `by` | reader's address: `<PLAN-ID> <item>` or manual reading date | empty → ERROR |
| `upstream_sha` | anchor: bytes against which the verdict was made | not sha256 → ERROR |
| `note` | the essence of the find in one line | no when `attention`/`risk` → ERROR |

**The block is placed by the one who READ the bundle**, and not the one who brought it: entry without address
(`by`) doesn't mean anything, but `clean`, stamped «by directory list», turns audit
into fiction. Silent `attention` is indistinguishable from a typo - so `note` is machine required.

**Anchor `upstream_sha`** describes the very bytes that the person read: `sha256` **named
bodies** (`body_path`), when the bundle calls it, otherwise - a collapse of the entire provenance database (pairs
`path:sha256` from `files[]`/`origins[]`, same construction as `audited_at`). It is stored
SEPARATE from `files[].sha256` and is not updated either `--apply`, neither `--resolve` — this is his whole
value (see below).

## Gate: `AUDIT_MISSING` and `AUDIT_STALE`

`--check` distinguishes **three different events** — and does not merge them, just as codes are not merged `10` and `11`:

| Nakhodka | What does it mean? | What to do |
|:--|:--|:--|
| drift (`10`) | upstream has moved relative to the recorded one `sha256` | transfer/accept upstream changes |
| `AUDIT_MISSING` | block `audit` no - no one read the bundle | read the entire bundle and write down the verdict |
| `AUDIT_STALE` | `audit.upstream_sha` lost anchor | reread the bundle and update the block `audit` |

Both finds go into the common triage channel: exit code **`11`**, key `triage` in `--json`.
«Not checked» and «clean» cease to be indistinguishable - this is the executable form of the rule
**«there is no vendor development without an audit»**.

::: tip Why is the anchor native and not derived
Previously, the decay of the verdict was DERIVATIVE: «bytes diverged from `audited_at`» was derived from
drift relative `files[].sha256`. After `--apply` fresh sha was recorded, the drift disappeared -
and the mark along with it, although the human verdict remained rancid. Own anchor
`audit.upstream_sha` `--apply` does not touch, so `AUDIT_STALE` **is worried** application
upstream (test `test_apply_refreshes_files_sha_but_audit_stale_survives`).
:::

Derived elevation `stale_verdicts` remained exactly for bundles **without** block `audit` (then
is for those who catch `AUDIT_MISSING`), and is printed clearly - two sources of the same
marks are not confused:

```
[stale]    <bundle>   (verdict)   bytes diverged from audited_at — human bundle verdict
                                 ROTTEN … (derived mark: block audit there is no bundle)
```

The script is still **does not read plan files**: verdict lives next to the skill, connections
«script `skiller` reads `plans/**`» no.

## The remediation boundary: what is repaired and what is accepted

Triage finds more than can be repaired, and this is the named boundary, not «didn't get around to it»:

> **What is remediated is what comes to the agent as RULES OF CONDUCT. What is not remedied is what
> appears as help or as a user artifact.**

- **rules of conduct** (skill instructs you to go online and apply what you received as
  instructions and output format) → remediation: vendor payload under `sha256` + `strategy: fork`,
  network channel is removed (see below, «Pinning and re-pinning»);
- **reference documentation** (WebFetch README alien SDK from branch `main`) — same class
  not pinned, but payload agent reads as **help**; fork of the official bundle for the sake of a pin
  doc-URL is disproportionate. Accepted class, the find remains visible;
- **third-party code in the USER artifact** (CDN in the generated report template) is being executed
  in his browser - outside the agent's trust loop and outside the loop `skiller`. Accepted class;
- **body of attack lines by purpose** (security skill guide) — constant
  triage redness is **property** gate, not a defect: weaken the rule for this bundle
  prohibited.

The accepted class is recorded as a verdict `attention` + `note` in the block `audit` bundle - that is
remains visible rather than disappearing from view.

## `kind: "reference-only"` — bundle that does not vendor anything

Machine sign: **all** `files[].path` are empty, that is, records are provenance-LINKS to external
specs, and the body of the skill is written by us. Such a bundle must be announced `kind: "reference-only"`
(`validate.sh` requires this in both directions), and he has `audit.upstream_sha` **omitted** —
there is nothing to anchor, there are no mirrors. The gate does not require it to have an anchor: otherwise the rule would start
to lie in a class that is instituted for the sake of honesty. `--check` prints such bundles separately
(`reference_only` in `--json`), because the denominator «N vendor bundles» is otherwise heterogeneous.

## Procedure for vendoring a new skill

1. **Read the entire bundle** — all files: `SKILL.md`/`body_path`, `references/**`,
   `snippets/**`, scripts, resources. Special attention: scripts, dependencies, any calls to
   to external network sources, as well as «unusual patterns» — calls and operations not responding
   stated purpose of the skill.
2. **Give a named verdict**: `clean` / `attention: <what exactly>` / `risk: <what exactly>`.
3. **Write provenance** — `upstream.json` next to `SKILL.md` (`root.reference-provenance`),
   source of patterns, if something is taken as a pattern - in `docs/reference.md`. **Ibid -
   block `audit`** with the verdict of step 2, the address of the reader and the anchor `upstream_sha`; without it
   `--check` gives `AUDIT_MISSING` and the bundle is not considered verified.
4. **Drive away `--check`** and analyze each triage trigger: either this is a find, or
   explained exception. Loosen the rule «to make it green», prohibited.
5. **Finding a class `risk` do not repair without permission** — name and escalate to owner.

**Verdict update** (after `AUDIT_STALE` or scheduled re-reading): re-read the bundle →
update `verdict`/`note` → put today's `at` and your address in `by` → recalculate
`upstream_sha` according to the current provenance base (or `sha256` `body_path`). The order is required:
`--check` **to** `--apply`, otherwise you will have to re-read other bytes.

## Known Trips and Bounds

- **The Security Skill Guide will always be lit.** Corps of attacking lines - his
  content; the rule was not relaxed for him. Consequence: «green triage throughout the registry»
  is not reachable by design.
- **Suppression mechanism/allowlist no.** This is the trust policy decision (what to count
  accepted exception) — subject to the owner's decision, not the script.
- **The rules are in English.** RU-only has a branch `PRM_REMOTE_INSTRUCTIONS`, because it's nearby
  locale-copies are not registry canon. The remaining rules on translations are not
  covered - known boundary.
- **The scan does not cover what is going on in runtime.** If a skill instructs you to go online for
  rules, sha256 bundle does not describe this surface. `PRM_REMOTE_INSTRUCTIONS` such a skill
  finds, but only a human can check the contents via the link.

## Provenance record without mirror

`files[]`-entry with empty `path` — **link to external spec**, not a local mirror: foreign
code was not vendored, check sha nothing. `--check` prints such an entry as a separate tag and
goes further:

```
[ref]      <bundle>   (no mirror)   reference-only provenance, sha is not verified: <url>
```

Count such a bundle «vendor» cannot: the integrity of its contents is not covered by anything.

## Pinning and re-pinning of external payload

When the bundle carries rules of conduct from the SECOND upstream (not the skill itself, but the content,
which the skill used to pull with a network and use as instructions - class `PRM_REMOTE_INSTRUCTIONS`),
nepinovka URL for a branch is insufficient: the branch does not catch content substitution, but deletion/privatization
of someone else's repository breaks the skill silently, and in both cases the integrity remains an EXTERNAL guarantee.
Closing - `strategy: fork` + payload vendor pristine-copy to `references/` under sha256,
downloaded strictly from **SHA-URL** (`.../<40-symbolic commit SHA>/...`), never `/main/`.
Example - `frontend/web-design-guidelines`, where `references/web-interface-guidelines.md`
(`body_path`) mirrors `vercel-labs/web-interface-guidelines` on the pinned commit.

**The upstream body, which ITSELF carries the instructional pattern, is not vendored by the mirror.**
If the upstream wrapper (for example, alien `SKILL.md`) was copied to `references/`
pristine-copy, this copy would go along with the skill to every fleet project and continue
carry the same removable instruction - the remediation would be formal, not actual. Therefore
the provenance of such a wrapper remains ONLY a machine readable record `files[]` with empty `path`
(see above, «reference-only provenance») — without a local copy of its contents; `sha not verified`
for her deliberately, and not by oversight. Triage rule (`PRM_REMOTE_INSTRUCTIONS` and the entire scan)
does not get exceptions for `body_path`/`references/**`/fork-mirrors for no remediation -
the bundle file is distributed throughout the fleet and read by the agent via the link, so «it's just a mirror»
does not reduce the risk.

Re-pinning procedure is MANUAL, `--apply` registry payload does not touch:

1. download new SHA-URL new commit;
2. check sha256 received bytes with the expected value BEFORE writing - discrepancy or
   means the wrong one SHA, or substitution, and in both cases the constant is not overwritten «to
   agreed» (anti-fitting);
3. update the corresponding entry `files[]` (`sha256`, `fetched_at`) and `notes` the same
   commit, which is the very fact of re-pinning.

Freshness is deliberately traded here for integrity: vendor payload does not follow
upstream automatically, the deprecation window is closed only by an explicit re-pin.

## Links

- [Upstream-sync](./upstream-sync.md) — strategies `replace`/`notify`/`fork`/`merge`, `--apply`, `--resolve`
- [Skills from packages](./vendor-skills.md) — distributing physical copies to the project
- `docs/reference.md` (repository root) — sources of external patterns
