# Antigravity independent audit — 2026-11-01

Status: **blocked for role execution**, including native binding projection,
conductor direct/planned routes and fallback. `launch argv` only renders a command;
it does not grant authority or prove that executing it is safe. No campaign delivery,
controller, live machine configuration, push or publication was changed.

The audit began on clean `main`, exactly `9e309d952402dfb80834fc1ada27e005eba6987f`.
Existing AGY/Codex/conductor processes were observed and left alone. Prior reports
were leads; the conclusions below use fresh local probes and code review.

## Live CLI evidence

Installed `agy --version`: **1.4.12**. `agy models` returned these selectors:

| Base selector | Listed effort suffixes | Independent bounded request |
| --- | --- | --- |
| `claude-sonnet-5-5` | low, medium, high | high: authentication required, exit 1, no init |
| `claude-opus-5-5` | low, medium, high | high: quota exhausted (429), exit 3 |
| `gemini-4-argon` | low, medium, high | low: unsupported user location (400), exit 3 |
| `gemini-3.8-flash` | low, medium, high | low: unsupported user location (400), exit 3 |

Requests used a private empty cwd, HOME and four XDG directories, no
permission-skipping flag, one NDJSON `user` message, `--input-format stream-json
--output-format stream-json --print-timeout 35s --print ''`, and a 45-second
process-group deadline. Prompts requested a fixed string without tools. No tool
execution was requested. No retry followed a stable quota/location rejection.
Low/medium/high listing is not proof of successful inference at those efforts.
`--effort xhigh --model claude-sonnet-5-5` returned exit 1 and an explicit invalid
selection with available values low/medium/high; it remains rejected in SKM.

Opus, Argon and Flash emitted init with the **base** model selector, then step
updates and an ERROR result. Observed conversation IDs respectively:
`d2fe875b-1800-450a-8f7a-0fa5c12c29ad`,
`447a5763-ac54-49b0-9d25-719906cde472`,
`9054c4ae-a167-4b5e-99a1-9c4d4b48787e`.
These are IDs of failed conversations, not successful executor sessions. Init
model evidence reports the CLI selection; it does not attest the inference backend.
Fresh raw stdout/stderr are retained locally at
`/home/vostrikov/.cache/skm-agy-audit/run-in7oxo6t/` (not a portable fixture).

Live AGY tool behavior under `--sandbox` could not be re-established while inference
was unavailable; prior sandbox reports are not treated as fresh proof.
No successful response or resume was established during this audit. CLI help offers
`--conversation ID`, but SKM deliberately has no AGY resume argv/capability; it must
not fabricate continuation or a session ID. Timeout/cancel integration tests use a
fake CLI to verify process-group termination and retention of observed init evidence;
they do not establish live inference or remote-daemon cancellation.

## Authority and reproducible canaries

Run from the repository, with a clean, short temporary root outside a project:

```sh
mkdir -p "$HOME/.cache/skm-tests-agy"
TMPDIR="$HOME/.cache/skm-tests-agy" python3 packages/orch/scripts/agy-boundary-probe.py
```

The probe creates only synthetic secrets, output files and TCP/Unix listeners in
its own temporary directory. It never contacts Docker or another user's daemon.
Exit zero means the diagnostic ran; `admission: unproven` remains authoritative.
Observed on this host:

| Boundary | Outside write | Host read | Host TCP listener | Host Unix daemon socket |
| --- | --- | --- | --- | --- |
| narrow Landlock, grandchild | denied EACCES | allowed | allowed | allowed |
| bwrap user + network namespace, read-only root bind | denied EROFS | allowed | refused ECONNREFUSED | allowed |

`unshare --user --map-root-user --net true` failed writing uid_map; **bwrap did
start**, so that one unshare failure does not prove namespaces are impossible here.
The bwrap probe is intentionally a network-only candidate, not a complete filesystem
sandbox. A minimal mount tree could hide host files and sockets, but it must also
account for inherited descriptors, process access, credentials and all provider tools.
AGY init lists file, shell, browser, MCP and subagent tools even with empty HOME/XDG.
HOME isolation alone therefore establishes neither tool absence nor daemon isolation.
No external daemon was stopped or reconfigured to obtain a passing result.

A plausible future design places the entire provider and descendants in a minimal
mount/PID/IPC/network boundary and brokers inference separately from tool execution.
Allowing the entire process general network access restores tool egress; denying all
network removes direct inference. An inference allowlist/proxy alone does not prove
that tools cannot use it. A trusted per-tool broker (including file, browser, MCP,
subagent and external daemon actions), or equivalent demonstrated separation, is
needed. This CLI integration has no verified mechanism providing that separation.
The blocker is **unproven end-to-end tool/inference authority separation**, not a claim
that this host can never support isolation. A live conductor pilot is consequently
not authorized by the implementation and was not performed.

## Repairs and regression evidence

- Route availability/fallback and native binding projections reject AGY authority
  regardless of user catalog argv or capability claims. The existing final role
  launch guard remains; rendering a catalog is not launch admission.
- Raw provider lines are nested under `agy.raw`; they cannot inject conductor
  `system`, `result` or `turn.completed` events. Original lines remain evidence.
- Normalized terminal output is held until EOF, validated init/session/model and
  successful CLI exit. Malformed, duplicate, unknown outcomes or a CLI lingering
  after a claimed success do not become successful work. ERROR returns nonzero.
- Timeout/cancel preserves observed model, session and tool/init evidence.
- Earlier AGY tests were pytest functions invisible to the unittest runner; the
  regression suite now runs under the project's actual test runner.

Independent review found the early-terminal/lingering success bug, native projection
admission gap, timeout evidence loss and undiscovered tests. Regression tests exercise
real bridge + conductor with a fake executable, including malicious raw events,
nonzero/duplicate/unknown outcomes, hangs and custom/fallback routes. These establish
software behavior only. Claude class selectors remain existing routing policy;
Gemini classes stay unverified. Planner's older actor grammar does not gain a pretend
AGY identity: catalog inventory and runnable route support remain separate.

For exact project verification results and local commit, consult the accompanying
completion report. The safe temporary root avoids foreign `/tmp/.git` and
`/tmp/.swissknifeman` markers; none of those files were deleted or checks relaxed.

## Project verification

Final `affected-tests.py --base 9e309d952^ --tier full --run -j 4` completed
successfully in a private mount namespace:

```sh
bwrap --bind / / --dev /dev --bind "$HOME/.cache/skm-agy-audit/private-tmp" /tmp \
  --setenv TMPDIR /tmp python3 scripts/affected-tests.py \
  --base 9e309d952^ --tier full --run -j 4
```

Passed: ecosystem boundaries, public hygiene, golden, baseline typecheck; full tests
and validators for all selected modules and their bridge partners. The runner selected these from the
pre-groundwork base, so the original provider changes were covered as well as repairs.
All selected unit tests executed (cache misses); no failed final check was hidden.
The focused AGY suite passed 20 tests; the synthetic boundary probe reproduced its
unproven admission result independently. Golden snapshots required no regeneration.

Earlier audit attempts were not green: HOME-cache TMPDIR exposed aicore's nearest
project ancestor and caused planner-orch fixture writes to be denied by Landlock;
that superseded run was cancelled. A first namespace attempt omitted `/dev` and git
failed to open `/dev/null`; a later attempt found a new cross-module path reference
in catalog prose, which was removed. That superseded run was also cancelled. The
final run used private `/tmp` plus `/dev`, with no foreign files removed or validation
weakened. Logs are in `$HOME/.cache/skm-agy-audit/affected*.log`.

`version-guard.py status` remains nonzero: inherited `NOT-BUMPED planner 0.34.1`.
The corresponding plan-engine diff between `v0.34.1` and `9e309d952` confirms those changes
predate this audit. No release/version migration or fleet publication was performed.
The release guard is not reported as passed. Live auth/quota/location refusals above
and absence of demonstrated isolation/resume remain blockers, independently of tests.
