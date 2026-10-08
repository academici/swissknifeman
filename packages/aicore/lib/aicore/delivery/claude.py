"""plugins — visibility marketplace-plugins Claude Code in the first turn.

`skiller budget --first-turn` sees only the design surface; plugin
is resident in EVERY session (~449/~450 current always-on,
 §3), but
is not taken into account by the meter. This module glues two terminals of someone else's CLI —
`claude plugin list --json` (enumeration, CWD-dependent, undocumented
flag) and `claude plugin details <id>` (Always-on-price, text output, your
`--json` no) — into one summary. Fail-loud: any failure gives `tokens=None`, and not
silent 0 (0 reads as «no plugins» and makes the meter false exactly
where it should warn)."""
import json
import re
import subprocess

from .quality.eval import CLAUDE_BIN_ENV, claude_bin

PLUGIN_CALL_TIMEOUT = 15

_ALWAYS_ON_RE = re.compile(r"(?m)^\s*Always-on:\s*~([\d,]+)\s*tok\b")

_details_cache = {}


def _run_claude(argv, *, cwd=None, timeout=PLUGIN_CALL_TIMEOUT):
    """Call `claude <argv>`. (ok, stdout|None, detail|None) — detail is full
    only on failure and gives the reason (fail-loud, not a silent failure)."""
    claude = claude_bin()
    if claude is None:
        return False, None, f"claude not found (see {CLAUDE_BIN_ENV}/PATH)"
    try:
        r = subprocess.run([claude, *argv], cwd=cwd, capture_output=True,
                           text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return False, None, f"claude {' '.join(argv)} — timeout {timeout}with"
    except OSError as error:
        return False, None, f"claude {' '.join(argv)} — {type(error).__name__}"
    if r.returncode != 0:
        return False, None, f"claude {' '.join(argv)} — code {r.returncode}"
    return True, r.stdout, None


def list_enabled_plugins(target):
    """Enabled-project plugins `target`, deduplicated by `id` (one `id`
    comes twice with different `scope` — `claude plugin list --json` resolve
    efficient set of PROJECT via `cwd=target`, parsing `enabledPlugins` from
    `settings.json` not done - rejected D142 construction). Returns
    (entries, status, detail): status — 'ok'|'n/a'; on 'n/a' detail calls
    reason. Records carry a field `errors` listing as is - classification
    `broken` vs `unparsed` requires EXODUS `details` and is resolved later, in
    `plugins_summary`, not here."""
    ok, stdout, detail = _run_claude(["plugin", "list", "--json"], cwd=str(target))
    if not ok:
        return [], "n/a", [detail]
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return [], "n/a", ["claude plugin list --json — invalid JSON"]
    if not isinstance(data, list):
        return [], "n/a", ["claude plugin list --json — expected list of entries"]
    dedup = {}
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("enabled") or not entry.get("id"):
            continue
        dedup.setdefault(entry["id"], entry)
    return list(dedup.values()), "ok", []


def plugin_always_on_tokens(plugin_id, cwd):
    """Always-on price for ONE plugin - single line `Always-on: ~N tok`
    output `claude plugin details <id>`. `details` resolve local-scope
    plugin ONLY for `cwd` of his project (RAG:✅ 2026-07-31 alive `claude
    2.1.220`: `architect@swissknifeman` — code 1 without `cwd`, code 0 under
    `cwd=memster`) — `cwd` REQUIRED parameter, guess about it internally
    module is disabled. The VALUE of the price does not change between CWD (checked
    on four out of two plugins CWD) → success cached by `id` globally,
    saving fan-out for the fleet; failure (resolution OR parsing) NOT cached -
    same `id` under another `cwd` will resolve again in the next call, otherwise
    the very first alien project would poison the cache for the entire run. Returns
    (tokens|None, detail|None); suffix (`~1.1k`) was not observed in the measurement - when
    regexp mismatch, the line goes to unparsed, multiplier is not guessed."""
    if plugin_id in _details_cache:
        return _details_cache[plugin_id]
    ok, stdout, detail = _run_claude(["plugin", "details", plugin_id], cwd=str(cwd))
    if not ok:
        return None, detail
    m = _ALWAYS_ON_RE.search(stdout)
    if not m:
        return None, f"{plugin_id}: string Always-on not recognized"
    tokens = int(m.group(1).replace(",", ""))
    result = (tokens, None)
    _details_cache[plugin_id] = result
    return result


def plugins_summary(target):
    """Summary always-on project plugins `target`:
    `{status, entries[], total, partial, unparsed[], broken[], warnings[]}`.
    `entries` — `{id, scope, tokens}` (tokens=None at the price not taken). `total`
    counts ONLY recognized records; `partial=True`, if at least one is not
    recognized (`unparsed`/`broken` are not empty) OR the entire listing was given n/a.
    Incompleteness - TWO different natures, do not mix in one list: `broken[]`
    (`{id, reason}`) — the listing itself declared the plugin broken (`errors`) AND
    `details` did not give a price; `unparsed[]` — details not recognized WITHOUT declared
    breakdowns (upstream format drift). Recording with `errors`, STILL gave away
    price, regular: included in `total`, `errors` — in `warnings[]`.
    Silent 0 is not in any thread."""
    plugins, status, list_warnings = list_enabled_plugins(target)
    if status != "ok":
        return {"status": "n/a", "entries": [], "total": None, "partial": True,
               "unparsed": [], "broken": [], "warnings": list_warnings}
    entries = []
    unparsed = []
    broken = []
    warnings = []
    total = 0
    for entry in plugins:
        pid = entry["id"]
        errors = entry.get("errors")
        tokens, error = plugin_always_on_tokens(pid, target)
        entries.append({"id": pid, "scope": entry.get("scope"), "tokens": tokens})
        if tokens is None:
            if errors:
                broken.append({"id": pid, "reason": "; ".join(errors)})
            else:
                unparsed.append(error)
        else:
            total += tokens
            if errors:
                warnings.append(f"{pid}: {'; '.join(errors)}")
    entries.sort(key=lambda e: (e["id"], e["scope"] or ""))
    return {"status": "ok", "entries": entries, "total": total,
           "partial": bool(unparsed or broken), "unparsed": unparsed,
           "broken": broken, "warnings": warnings}
