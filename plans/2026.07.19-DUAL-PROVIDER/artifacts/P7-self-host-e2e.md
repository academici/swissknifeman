# P7.2 self-host E2E — D121 live transaction result

**Observed:** 2026-07-23  
**Session:** `gpt-5.6-terra/high`; approval `never`; sandbox `danger-full-access`.
**Authority:** D121 exact S1+O1 inventory only; D124 accepts D123/P6.12 as its predecessor.

## Isolated and native evidence

- The worktree-local public instruction matrix wrote only
  `/tmp/p72-rerun.Sv13U8/instruction-conformance.md` (SHA-256
  `60686d05fa8bf9830cad8a960782ce12cdcb369a44b49cd9b864db481bde453e`): Claude-only,
  Codex-only and dual-provider rows are GREEN; dual parity is 49 common IDs and 18 owned
  extensions. Managed-drift repair preserved outside bytes and implicit full access refused.
- The accepted D120 ordinary authenticated marketplace/plugin proof remains the native Codex
  carrier. It is historical evidence only; no marketplace action was repeated here.
- Focused disposable D108 regressions passed: core provider-lock `28/28` and mAInd
  provider/deploy `55/55` tests.

## Live D121 cycle

The live no-write plan was admitted with the exact chain
`.codex/hooks.json=update`, `.codex/hooks/lifecycle.py=create`, `.mcp.json=noop` and two
planned provider rows. The first apply created only the following D121 state:

| Path | Applied SHA-256 / result |
|:--|:--|
| `.swissknife.json` | `038df16566812f7e0ec40e84b177b5eeb534d2e6d6122fffee9ba6d7e3fb8909` |
| `.codex/hooks.json` | `29ff242eaddc67964584b53abba361e0c384aa1d7d799520f9e8b75deaed43f7` |
| `.codex/hooks/lifecycle.py` | `467e207ff17d912215cbdb912ea378d004dfa1bdecb50df0278b014a4d48ca51`; compile and `--surface context.observer` smoke passed |
| `.mcp.json` | noop; sealed SHA-256 `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283` unchanged |
| `.swissknifeman/provider-artifacts.lock.json` | `56f9d44063ae261d151b504259a0e950d6f5ae5b0a17c0e08015773c5c20bcf9`; exactly three records |

The immediate same-plan recheck produced `noop`, `noop`, `noop`; applying it left the full
five-path applied inventory byte-identical. The explicit D123 rollback then restored the
sealed preimage: `.swissknife.json`, handler and lock absent; hooks SHA-256
`7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`; MCP SHA-256 unchanged;
both named transaction backups absent. No other provider target was applied.

## Final gates

- `bash packages/{skiller,task,harness,maind,analyst}/scripts/validate.sh` — GREEN.
- `PYTHONPATH=. python3 -m unittest discover -s core/tests` — GREEN.
- `maind health --cwd --json` — connected; memory, mAInd MCP and code MCP GREEN.
- Protected `plans/2026.07.18-FOREMAN/**` and `plans/ACTIVE.md` delta: 0; plan-lint: 0 ERROR,
  2 inherited WARN, 0 new warnings.

**Verdict:** GREEN — P7.2 satisfies the approved D121 apply, idempotence and explicit rollback
rehearsal without widening its live authority.
