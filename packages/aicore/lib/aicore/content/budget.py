"""Context budget: token estimate, skill and set budgets, listing budget, measurements and first-turn sources.

Token scoring is ROUGH and language dependent (Cyrillic is denser than Latin in the Claude tokenizer),
stdlib-only, without third-party tokenizers. The number suits COMPARING sets and relative weights, not
accurate counting. This module is the single source of the token math; callers compose it with their own
skill selection and host data (for example ``host_servers`` of :func:`measure_mcp`).
"""
import json
import math
import os
import subprocess
from datetime import timedelta
from pathlib import Path

from ..util import timefmt
from ..util.term import die
from .skill import read_frontmatter, split_frontmatter

# Characters per token - DIFFERENT for Cyrillic and Latin/code: Cyrillic for tokenizer
# Claude denser, Latin/code/punctuation - less common. Therefore EN-canon is cheaper RU when
# THE SAME volume of text - this is the gain of translation. Roughly, to compare sets,
# not accurate accounting (oracle - /v1/messages/count_tokens).
#
# Calibration (RAG, verified 2026-07-02, perplexity — 3 source: codeusagecalc,
# frontiersin 2025, basicfreetools; audit B-1): Cyrillic prose ~2.8–3.2 chars/tok,
# Latin prose ~3.5–4.0, code ~2.5–3.0. Legacy 2.2/4.0 underestimated RU chars/tok
# (=overestimated RU-tokens, artificially inflating «transfer winnings») and overestimated LAT
# chars/tok (=undervalued tokens code-heavy tel). CYR — mid range (2.9). LAT —
# compromise EN-prose and code with one constant (model does not distinguish between code blocks inside
# bodies): skill bodies technical (commands/snippets/tables) → is closer to code than to
# pure prose (3.4).
CHARS_PER_TOKEN_CYR = 2.9
CHARS_PER_TOKEN_LAT = 3.4
CONTEXT_LIMIT = 200_000
TOP_N = 10


# --- token valuation -----------------------------------------------------------
def estimate_tokens(text):
    """Language-sensitive token evaluation: Cyrillic ~2.9 chars/tok, rest ~3.4
    (see calibration above). 0 for empty. EN thus cheaper RU with equal
    volume (transfer winnings)."""
    if not text:
        return 0
    # U+0400–04FF (Cyrillic) — RU/UK and most Slavic languages; U+0500–052F
    # (Cyrillic Supplement) — add. letters (Komi-Permyak and others.), B-3: not before
    # taken into account (under-counting of tokens for text with these letters).
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ" or "Ԁ" <= c <= "ԯ")
    return math.ceil(cyr / CHARS_PER_TOKEN_CYR + (len(text) - cyr) / CHARS_PER_TOKEN_LAT)


def skill_budget(skill_dir):
    """Three-tier budget for one skill (directory with SKILL.md).
    → {name, tier0, tier1, tier2, snippets, references}; None, if SKILL.md
    is missing. tier2 (⌥ on-demand) — amount snippets/ AND references/: both
    are loaded BY LINK from the body (navigator), non-resident - same semantics,
    one glob-pattern (P2.1 SKM-MASTER-003, T1: after thin-navigator-waves
    P7 SKM-MASTER-002 bodies of monoliths lie in references/full.md — excluding
    here tier-2 is understated, «single source of token mathematics» lies)."""
    skill_dir = Path(skill_dir)
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return None
    text = md.read_text(encoding="utf-8-sig")
    fm = read_frontmatter(md)
    name = fm.get("name", "") or skill_dir.name
    desc = fm.get("description", "")
    _, body = split_frontmatter(text)

    def _on_demand_files(subdir):
        d = skill_dir / subdir
        return [p for p in sorted(d.glob("*"))
                if p.is_file() and p.name != "index.json"] if d.is_dir() else []

    snippets = _on_demand_files("snippets")
    references = _on_demand_files("references")
    tier2 = sum(estimate_tokens(p.read_text(encoding="utf-8", errors="ignore"))
                for p in (*snippets, *references))
    return {
        "name": name,
        "tier0": estimate_tokens(name + " " + desc),
        "tier1": estimate_tokens(body),
        "tier2": tier2,
        "snippets": len(snippets),
        "references": len(references),
    }


def budget_for_set(skills, pulled=None):
    """Aggregate a three-tier budget by a list of skills [(bucket, rel, dir,
    fm_name)]. Returns dict with amounts, breakdown by bucket and items."""
    pulled = pulled or {}
    items, by_bucket = [], {}
    for bucket, _rel, d, fm_name in skills:
        b = skill_budget(d)
        if b is None:
            continue
        key = fm_name or Path(d).name
        rec = {"bucket": bucket, "name": b["name"], "tier0": b["tier0"],
               "tier1": b["tier1"], "tier2": b["tier2"], "snippets": b["snippets"],
               "references": b["references"], "transitive": key in pulled}
        items.append(rec)
        agg = by_bucket.setdefault(
            bucket, {"tier0": 0, "tier1": 0, "tier2": 0, "count": 0})
        for k in ("tier0", "tier1", "tier2"):
            agg[k] += b[k]
        agg["count"] += 1
    tier0 = sum(i["tier0"] for i in items)
    tier1 = sum(i["tier1"] for i in items)
    tier2 = sum(i["tier2"] for i in items)
    return {
        "count": len(items),
        "transitive": sum(1 for i in items if i["transitive"]),
        "tier0": tier0, "tier1": tier1, "tier2": tier2,
        "if_all_triggered": tier0 + tier1,
        "by_bucket": by_bucket,
        "items": items,
    }


# --- first-turn footprint --------------------
# Invisible always-on budget - the root cause of the incident (
# RAG:✅ 2026-07-12). Five sources always-on loads of the first move of the project:
# skills meta (⊕ tier-0), .claude/agents description, CLAUDE.md + path-less rules,
# live run SessionStart-hooks, MCP tool-defs.
#
# Thresholds re-issued 2026-07-31
# vs baseline fleet -,
# n=22, anchor 3003d352. Previous pair 7,000/10 000 was calibrated at a value that
# DID NOT count marketplace-plugins (there was nothing to count them before P1.1), and therefore gave
# WARN at 95 % fleet: gate, red for everyone, does not distinguish normal from accident. Median
# plug-in amount for the fleet is 8,741 current, so the threshold for
# plugin-inclusive value is 7,000 + 8 741 ≈ 16 000, and the stripe saves
# old attitude warn/target 1,43 → 23 000. Fleet distribution on the new pair
# (session_total): OK 23 % · ELEVATED 32 % · WARN 45 %.
FIRST_TURN_TARGET_MAX = 16_000
FIRST_TURN_WARN = 23_000
HOOK_TIMEOUT = 10

# Known external MCP-servers → number tool-schemes resident in system prompt (rude).
# Servers of the host repository come first from host `mcp_servers` (exact data owned
# by the host). Unknown server from
# .mcp.json — FALLBACK_MCP_TOOLS (flat-rating, not 0 and not overstated). `boost` —
# alias `laravel-boost`, spotted at vintera/cms (one distribution, two server names
# in the fleet - P2.3 Scope Included).
KNOWN_MCP_TOOLS = {
    "perplexity-web": 4, "context7": 2, "sequential-thinking": 1,
    "fetch": 1, "memory": 9, "filesystem": 11, "github": 20, "playwright": 21,
    "serena": 20, "laravel-boost": 15, "boost": 15,
}
FALLBACK_MCP_TOOLS = 5
TOKENS_PER_MCP_TOOL = 150

# --- mode-dependent cost model MCP ---------------------
# RAG:✅ 2026-07-31 <https://code.claude.com/docs/en/mcp> §«Scale with MCP tool
# search» + <https://code.claude.com/docs/en/context-window> §«MCP tools
# (deferred)» + <https://code.claude.com/docs/en/features-overview> §«Context
# cost by feature»: tool search enabled BY DEFAULT (deferred) — at the start
# sessions are resident only tool NAMES + server instructions, complete
# schemes are loaded upon request; `ENABLE_TOOL_SEARCH=auto` — threshold mode
# (loads circuits forward if they fit within 10% model context window);
# `ENABLE_TOOL_SEARCH=false` — old model, all schemes forward (TOKENS_PER_MCP_TOOL
# above - this thread). The variable is NOT exposed anywhere in the repository -
# the meter only READS it.
ENABLE_TOOL_SEARCH_ENV = "ENABLE_TOOL_SEARCH"
MCP_MODE_DEFERRED = "deferred"
MCP_MODE_AUTO = "auto"
MCP_MODE_OFF = "off"
MCP_MODE_SOURCE_DEFAULT = "default"

# Resident name of the tool in deferred-mode - LOWER limit, not measurement:
# `context-economy/SKILL.md:89` already carries a number «lazy tool-search cuts schemas
# ~84%» (the same fact that prose knows `mcp-advisor/SKILL.md:113-117`) —
# 150 current/diagram × (1 − 0.84) ≈ 24 current/name. Accuracy is not ours (repository not
# sees `/context` from within the agent, RAG:— repo-grounded `findings/…probe §9`).
TOKENS_PER_MCP_TOOL_NAME = 24
# Server instructions when their text is NOT available locally (external binary/
# package, e.g. perplexity-web/serena) — rough fallback on short block
# instructions for one server (symmetrical FALLBACK_MCP_TOOLS for the age model):
# is not 0 and not overestimated.
FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS = 40


def mcp_tool_count(name, host_servers):
    """Tool count: host data, then KNOWN_MCP_TOOLS, then FALLBACK_MCP_TOOLS."""
    server = host_servers.get(name)
    if server is not None and server.tools is not None:
        return server.tools
    return KNOWN_MCP_TOOLS.get(name, FALLBACK_MCP_TOOLS)


def mcp_instruction_tokens(name, host_servers):
    """Server instruction tokens: host data checked against the server's own source
    (e.g. an `initialize` without `instructions` is 0, not a fallback), otherwise
    FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS."""
    server = host_servers.get(name)
    if server is not None and server.instructions_tokens is not None:
        return server.instructions_tokens
    return FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS


def tool_search_mode(target):
    """Effective mode tool search: process environment → `env` in
    `.claude/settings.local.json` → `env` in `.claude/settings.json` → default
    «enabled» (D22, Implementation Rules P2.3 §2). Returns (mode, source);
    source is printed in the report - a number without an origin is not published."""
    val = os.environ.get(ENABLE_TOOL_SEARCH_ENV)
    source = "env" if val is not None else None
    if val is None:
        target = Path(target)
        for fname in ("settings.local.json", "settings.json"):
            f = target / ".claude" / fname
            if not f.is_file():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            v = data.get("env", {}).get(ENABLE_TOOL_SEARCH_ENV)
            if v is not None:
                val, source = v, fname
                break
    if val is None:
        return MCP_MODE_DEFERRED, MCP_MODE_SOURCE_DEFAULT
    val_norm = str(val).strip().lower()
    if val_norm == "auto":
        return MCP_MODE_AUTO, source
    if val_norm in ("false", "0", "off"):
        return MCP_MODE_OFF, source
    return MCP_MODE_DEFERRED, source

# --- listing budget model Claude Code (P3.4, RAG:✅ /docs/en/skills) ----
# «The listing always contains every skill name … Claude Code shortens
# descriptions to fit the listing's character budget … drops descriptions
# starting with the skills you invoke least.» The client cuts each record BEFORE
# 1 536 char (description+when_to_use; name — always completely) and keeps the amount
# listing under the ceiling budget = context_window * fraction (default 1%,
# configured `skillListingBudgetFraction`/`SLASH_COMMAND_TOOL_CHAR_BUDGET` —
# both are parameterizable here, not hardwired, see Implementation Rules P3.4).
# Order «drop» depends on the project's call history, which we don't have -
# `_measure_skills` SIMULATES a ceiling (post-budget = min(amount, ceiling)),
# not the drop order of specific records; this is Scope Included P3.4, not complete
# client simulation.
SKILL_LISTING_MAX_ENTRY_CHARS = 1_536
SKILL_LISTING_BUDGET_FRACTION = 0.01
SKILL_LISTING_CONTEXT_WINDOW = 1_000_000

# --- listing budget model Codex (P3.4, RAG:✅ learn.chatgpt.com/docs/build-skills,
# 2026-07-29) --------------------------------------------------------------------------
# «The skills list uses at most 2% of the model's context window, or 8,000 characters when
# the context window is unknown.» / «If many skills are installed, Codex shortens skill
# descriptions first. For large skill sets, Codex may omit some skills from the initial list
# and show a warning.» UNIT - SYMBOLS directly (not tokens, not translated ×3, like
# Claude Code above) — units of the two models DO NOT mix. Real context window,
# which Codex CLI thinks «known» for current model, not measured (round-trip out
# scope, D3) — therefore the calculation is always carried out according to the WORST case: the fallback budget, and not according to
# `CODEX_LISTING_BUDGET_FRACTION * window` (dependency on real window - [UNVERIFIED],
# see). Per-entry cap to write Codex original source not
# calls (unlike `SKILL_LISTING_MAX_ENTRY_CHARS` y Claude) — measures the raw amount.
CODEX_LISTING_FALLBACK_CHARS = 8_000
CODEX_LISTING_BUDGET_FRACTION = 0.02

LISTING_PROVIDERS = ("claude-code", "codex", "cursor", "grok", "antigravity")
CHAR_LISTING_PROVIDERS = frozenset({"codex", "cursor", "grok", "antigravity"})
DEFAULT_LISTING_PROVIDER = "claude-code"

MEASUREMENT_SURFACES = frozenset({"listing", "loaded-body", "runtime"})
MEASUREMENT_CLASSES = frozenset({
    "exact", "estimate", "lower-bound", "upper-bound", "unknown",
})
MEASUREMENT_STATUSES = frozenset({"pass", "over-budget", "stale", "unknown"})
MEASUREMENT_TTL = timedelta(days=30)

# --- which records are NOT included in the resident listing --------------
# Re-issue of the model based on stand OBSERVATION P3.1/P3.6 on live 2.1.220, not on
# doc (`plan.md` §2 «External fact rule»). Both fields removed the entire entry,
# delta rendered byte-for-byte in both runs:
# • `disable-model-invocation: true` — axis A −88
# (§3.2), same
# says first-party doc: «Description **not** in context»
#     (<https://code.claude.com/docs/en/skills> §«Control who invokes a skill»);
# • `paths:` — axis A −88, SAME value (ibid. §3.1/§4). Doku this
# contradicts («The listing always contains every skill name»), therefore
# basis - observation. Dosage metering P3.6 named the mechanism: (C) conditional
# loading with condition «session READ matched file», and NOT «file is in
# tree» (`findings/P3-paths-mechanism.md` §2). Condition for TREE in the model
# not entered: shoulder A1 dosage measurement («the matched file is located») gave
# «indistinguishable» in both runs - no record returned (ibid. §3), a
# unproven underestimation is worse than known overestimation (Implementation Rules
# P3.2 §2). On the FIRST move there are no read files by construction, so for
# first-turn-models are definitely an exception.
# Margins NOT measured for Codex (the stand only drove Claude Code — client version
# as the first line of the verdict file), so the exception ONLY applies to
# provider `claude-code`; codex-thread deliberately continues to overestimate.
LISTING_EXCLUDED_BY_FIELDS = ("disable-model-invocation", "paths")
LISTING_EXCLUSION_PROVIDERS = ("claude-code",)


def listing_exclusion(skill_dir):
    """Field frontmatter, for which the skill record is NOT included in the resident one
    listing Claude Code, or None. Check procedure = order
    `LISTING_EXCLUDED_BY_FIELDS`; the first match is the reason (entry
    is removed once, there are no two reasons for one entry)."""
    md = Path(skill_dir) / "SKILL.md"
    if not md.is_file():
        return None
    try:
        fm = read_frontmatter(md)
    except Exception:
        return None
    if str(fm.get("disable-model-invocation", "")).strip().lower() == "true":
        return "disable-model-invocation"
    if fm.get("paths"):
        return "paths"
    return None


def split_listing_entries(dirs, provider=DEFAULT_LISTING_PROVIDER):
    """(listed directories, {reason field: [directories]}) for the provider.
    Provider out `LISTING_EXCLUSION_PROVIDERS` — there are no exceptions at all (fields for
    not measured)."""
    if provider not in LISTING_EXCLUSION_PROVIDERS:
        return list(dirs), {}
    included, excluded = [], {}
    for d in dirs:
        field = listing_exclusion(d)
        if field is None:
            included.append(d)
        else:
            excluded.setdefault(field, []).append(d)
    return included, excluded


def format_listing_exclusions(excluded_by):
    """Canonical line for reporting excluded records (`{field: N}`) —
    ONE form for first-turn and for `--provider`-report so that the number of exceptions
    did not differ between the two seals."""
    if not excluded_by:
        return "excluded entries: 0"
    total = sum(excluded_by.values())
    by = ", ".join(f"{f}: {n}" for f, n in sorted(excluded_by.items()))
    return f"excluded records: {total} (by field {by})"


def listing_entry_tokens(skill_dir):
    """⊕ tier-0 ONE listing entry, as the client believes: `name` without trimming +
    `description`(+`when_to_use`, if the frontmatter carries the field), dripped to
    SKILL_LISTING_MAX_ENTRY_CHARS characters. Separate from `skill_budget.tier0`
    (is used `budget_for_set`/`--check-core`/budget map - that math
    out Scope P3.4, Files item'but doesn't touch her)."""
    skill_dir = Path(skill_dir)
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return 0
    fm = read_frontmatter(md)
    name = fm.get("name", "") or skill_dir.name
    desc_text = (fm.get("description", "") + " " + fm.get("when_to_use", "")).strip()
    return estimate_tokens(name) + estimate_tokens(
        desc_text[:SKILL_LISTING_MAX_ENTRY_CHARS])


def listing_entry_chars(skill_dir):
    """Listing entry Codex in RAW SYMBOLS: `name` + `description`(+`when_to_use`),
    WITHOUT cap - the original source does not give numbers for Codex (in contrast to 1,536 Claude
    Code), therefore, an honest measurement is a raw amount, an unguessed ceiling."""
    skill_dir = Path(skill_dir)
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return 0
    fm = read_frontmatter(md)
    name = fm.get("name", "") or skill_dir.name
    desc_text = (fm.get("description", "") + " " + fm.get("when_to_use", "")).strip()
    return len(name) + len(desc_text)


def measure_listing_budget(skills, provider=DEFAULT_LISTING_PROVIDER):
    """Provider-aware detection budget (listing) for active skill set
    `[(bucket, rel, dir, fm_name)]`. Two models, two units - DO NOT mix
: Claude Code — 1% context window in TOKENS (see `listing_entry_tokens`);
    Codex — fallback 8,000 CHARACTERS (worst case - real window [UNVERIFIED], D3).
    Records removed from listing by native field (`LISTING_EXCLUDED_BY_FIELDS`,
    P3.2/D95/D96), in `raw` are not included; their number and price come ADDITIVE
    keys `excluded`/`excluded_by`/`excluded_raw` (D16 — meaning of the previous keys
    does not change).
    → {provider, unit, raw, budget, over, degradation, excluded, excluded_by,
       excluded_raw}."""
    if provider not in LISTING_PROVIDERS:
        die(f"unknown --provider: {provider} (expected: "
            f"{', '.join(LISTING_PROVIDERS)})")
    all_dirs = [d for _bucket, _rel, d, _fm in skills]
    dirs, excluded = split_listing_entries(all_dirs, provider)
    entry = listing_entry_chars if provider in CHAR_LISTING_PROVIDERS else listing_entry_tokens
    if provider in CHAR_LISTING_PROVIDERS:
        budget = CODEX_LISTING_FALLBACK_CHARS
        unit = "char"
        degradation = "skill can be removed from the listing entirely"
    else:
        budget = int(SKILL_LISTING_CONTEXT_WINDOW * SKILL_LISTING_BUDGET_FRACTION)
        unit = "current"
        degradation = "description is truncated, name remains"
    raw = sum(entry(d) for d in dirs)
    excluded_raw = sum(entry(d) for ds in excluded.values() for d in ds)
    return {"provider": provider, "unit": unit, "raw": raw, "budget": budget,
            "over": raw > budget, "degradation": degradation,
            "excluded": sum(len(ds) for ds in excluded.values()),
            "excluded_by": {f: len(ds) for f, ds in sorted(excluded.items())},
            "excluded_raw": excluded_raw}


def measurement_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("SKILL_MEASUREMENT_TIMESTAMP_INVALID")
    parsed = timefmt.parse_rfc3339(value)
    if parsed is None:
        raise ValueError("SKILL_MEASUREMENT_TIMESTAMP_INVALID")
    return parsed


def measurement_number(value, *, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("SKILL_MEASUREMENT_VALUE_INVALID")
    if not math.isfinite(value):
        raise ValueError("SKILL_MEASUREMENT_VALUE_INVALID")


def make_measurement(*, provider, surface, value, unit, method, uncertainty,
                     measurement_class, observed_at, expires_at, source_id,
                     threshold, evaluated_at=None, model=None, model_family=None):
    """Build one closed provider-qualified measurement row.

    The row carries exactly one model identity and keeps its own unit/class and
    provider/surface threshold.  No cross-row arithmetic is performed here.
    ``unknown`` is the sole class permitted to use a null value.
    """
    for label, item in {
            "provider": provider, "unit": unit, "method": method,
            "uncertainty": uncertainty, "source_id": source_id}.items():
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"SKILL_MEASUREMENT_{label.upper()}_INVALID")
    if surface not in MEASUREMENT_SURFACES:
        raise ValueError("SKILL_MEASUREMENT_SURFACE_INVALID")
    if measurement_class not in MEASUREMENT_CLASSES:
        raise ValueError("SKILL_MEASUREMENT_CLASS_INVALID")
    identities = [item for item in (model, model_family) if item is not None]
    if len(identities) != 1 or not isinstance(identities[0], str) or not identities[0].strip():
        raise ValueError("SKILL_MEASUREMENT_MODEL_IDENTITY_INVALID")
    measurement_number(value, nullable=measurement_class == "unknown")
    if (measurement_class == "unknown") != (value is None):
        raise ValueError("SKILL_MEASUREMENT_CLASS_VALUE_MISMATCH")
    measurement_number(threshold)
    observed = measurement_timestamp(observed_at)
    expires = measurement_timestamp(expires_at)
    if expires <= observed:
        raise ValueError("SKILL_MEASUREMENT_FRESHNESS_INVALID")
    evaluated = measurement_timestamp(evaluated_at or observed_at)
    if evaluated >= expires:
        status = "stale"
    elif measurement_class == "unknown":
        status = "unknown"
    elif value > threshold:
        status = "over-budget"
    else:
        status = "pass"
    row = {
        "provider": provider,
        "surface": surface,
        "value": value,
        "unit": unit,
        "method": method,
        "uncertainty": uncertainty,
        "measurement_class": measurement_class,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "source_id": source_id,
        "status": status,
        "threshold": threshold,
    }
    row["model" if model is not None else "model_family"] = identities[0]
    return row


def aggregate_measurements(rows):
    """Validate and deterministically order independent measurement rows.

    Aggregation never sums rows.  A provider/model/surface may carry bounds as
    separate observations, but exact and estimated values (or differing units)
    cannot coexist under one identity because that would invite a mixed scalar.
    Provider IDs are open: a third provider needs rows, not a schema change.
    """
    accepted = []
    by_identity = {}
    thresholds = {}
    expected_base = {
        "provider", "surface", "value", "unit", "method", "uncertainty",
        "measurement_class", "observed_at", "expires_at", "source_id",
        "status", "threshold",
    }
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("SKILL_MEASUREMENT_ROW_INVALID")
        model_keys = {key for key in ("model", "model_family") if key in row}
        if len(model_keys) != 1 or set(row) != expected_base | model_keys:
            raise ValueError("SKILL_MEASUREMENT_SCHEMA_INVALID")
        rebuilt = make_measurement(
            provider=row["provider"], surface=row["surface"], value=row["value"],
            unit=row["unit"], method=row["method"], uncertainty=row["uncertainty"],
            measurement_class=row["measurement_class"], observed_at=row["observed_at"],
            expires_at=row["expires_at"], source_id=row["source_id"],
            threshold=row["threshold"], evaluated_at=(
                row["expires_at"] if row["status"] == "stale" else row["observed_at"]),
            **{key: row[key] for key in model_keys},
        )
        if rebuilt["status"] != row["status"] or row["status"] not in MEASUREMENT_STATUSES:
            raise ValueError("SKILL_MEASUREMENT_STATUS_INVALID")
        model_key = next(iter(model_keys))
        identity = (row["provider"], model_key, row[model_key], row["surface"])
        threshold_key = (row["provider"], row["surface"], row["unit"])
        if (threshold_key in thresholds
                and thresholds[threshold_key] != row["threshold"]):
            raise ValueError("SKILL_MEASUREMENT_THRESHOLD_CONFLICT")
        thresholds[threshold_key] = row["threshold"]
        peers = by_identity.setdefault(identity, [])
        if any(peer["measurement_class"] == row["measurement_class"] for peer in peers):
            raise ValueError("SKILL_MEASUREMENT_DUPLICATE")
        classes = {peer["measurement_class"] for peer in peers} | {row["measurement_class"]}
        if {"exact", "estimate"} <= classes:
            raise ValueError("SKILL_MEASUREMENT_CLASS_MIXED")
        if any(peer["unit"] != row["unit"] for peer in peers):
            raise ValueError("SKILL_MEASUREMENT_UNIT_MIXED")
        peers.append(row)
        accepted.append(dict(row))
    ordered = sorted(accepted, key=lambda row: (
        row["provider"], "model" not in row,
        row.get("model", row.get("model_family", "")), row["surface"],
        row["measurement_class"], row["source_id"],
    ))
    return {
        "status": "green" if ordered and all(
            row["status"] == "pass" for row in ordered) else "non-green",
        "rows": ordered,
    }


def listing_measurements(skills, *, observed_at=None, evaluated_at=None):
    """Current Claude/Codex listing estimates as typed independent rows."""
    observed = timefmt.utc_stamp(measurement_timestamp(observed_at) if observed_at else None)
    expires = (measurement_timestamp(observed) + MEASUREMENT_TTL).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for provider in LISTING_PROVIDERS:
        legacy = measure_listing_budget(skills, provider)
        rows.append(make_measurement(
            provider=provider,
            model_family="unknown",
            surface="listing",
            value=legacy["raw"],
            unit="characters" if provider in CHAR_LISTING_PROVIDERS else "estimated_tokens",
            method=("skiller:listing-characters-v1" if provider in CHAR_LISTING_PROVIDERS
                    else "skiller:listing-token-estimate-v1"),
            uncertainty=("exact source characters; provider loading is estimated"
                         if provider in CHAR_LISTING_PROVIDERS else "heuristic token estimate"),
            measurement_class="estimate",
            observed_at=observed,
            expires_at=expires,
            source_id="skiller.budget.listing",
            threshold=legacy["budget"],
            evaluated_at=evaluated_at or observed,
        ))
    return aggregate_measurements(rows)


def format_listing_report(report):
    """Human-readable string `measure_listing_budget` for CLI (--profile + --provider)."""
    status = "BREAKTHROUGH" if report["over"] else "ok"
    ratio = (f" (×{report['raw'] / report['budget']:.1f})"
             if report["over"] and report["budget"] else "")
    lines = [
        "", f"─── Discovery budget (listing), provider: {report['provider']} ───",
        f"Listing: {report['raw']} {report['unit']}  vs  budget {report['budget']} "
        f"{report['unit']}  — {status}{ratio}"]
    if report.get("excluded"):
        lines.append(f"{format_listing_exclusions(report['excluded_by'])} — "
                     f"{report['excluded_raw']} {report['unit']} not listed")
    lines += [f"Degradation mode: {report['degradation']}", ""]
    return "\n".join(lines)


def measure_agents(target, provider=DEFAULT_LISTING_PROVIDER):
    """name+description each .claude/agents/*.md (frontmatter) — same
    always-on «tax», the same as for skills, but for project subagents."""
    if provider == "codex":
        return {"tokens": 0,
                "detail": "Codex repo agents are provider-managed, not .claude/agents"}
    d = Path(target) / ".claude" / "agents"
    if not d.is_dir():
        return {"tokens": 0, "detail": "no .claude/agents"}
    total, count = 0, 0
    for p in sorted(d.glob("*.md")):
        try:
            fm = read_frontmatter(p)
        except Exception:
            continue
        total += estimate_tokens(f"{fm.get('name', p.stem)} {fm.get('description', '')}")
        count += 1
    return {"tokens": total, "detail": f"{count} agents"}


def measure_claude_md(target):
    """CLAUDE.md project + .claude/rules/**/*.md WITHOUT `paths:` (path-scoped rules
    not always-on — are loaded only on the affected file, see skill-authoring/
    context-economy canon). `**` — subdirectories `.claude/rules/` too always-on
    source (upstream: «subdirectories … are discovered automatically»,
    RAG:✅ `findings/…probe §6`) — flat `*.md` missed them (P2.3 find)."""
    target = Path(target)
    total, parts, n_rules = 0, [], 0
    claude_md = target / "CLAUDE.md"
    if claude_md.is_file():
        try:
            t = estimate_tokens(claude_md.read_text(encoding="utf-8", errors="ignore"))
            total += t
            parts.append(f"CLAUDE.md={t}")
        except Exception:
            parts.append("CLAUDE.md=n/a")
    rules_dir = target / ".claude" / "rules"
    if rules_dir.is_dir():
        for p in sorted(rules_dir.glob("**/*.md")):
            try:
                fm = read_frontmatter(p)
            except Exception:
                continue
            if fm.get("paths"):
                continue
            total += estimate_tokens(p.read_text(encoding="utf-8", errors="ignore"))
            n_rules += 1
    detail = " + ".join(parts) if parts else "no CLAUDE.md"
    if n_rules:
        detail += f" + {n_rules} rules without paths"
    return {"tokens": total, "detail": detail}


def measure_instructions(target, provider=DEFAULT_LISTING_PROVIDER):
    if provider == "claude-code":
        value = measure_claude_md(target)
        value["surface"] = "CLAUDE.md + .claude/rules"
        return value
    target = Path(target)
    agents_md = target / "AGENTS.md"
    if not agents_md.is_file():
        return {"tokens": 0, "detail": "no AGENTS.md", "surface": "AGENTS.md"}
    try:
        tokens = estimate_tokens(agents_md.read_text(encoding="utf-8", errors="ignore"))
    except OSError as error:
        return {"tokens": None, "detail": f"n/a ({error})", "surface": "AGENTS.md"}
    return {"tokens": tokens, "detail": f"AGENTS.md={tokens}", "surface": "AGENTS.md"}


def settings_hook_commands(target, event="SessionStart"):
    """Hook commands `event` from .claude/settings.json + settings.local.json
    (merge, both read - local can add hooks on top settings.json)."""
    target = Path(target)
    cmds = []
    for fname in ("settings.json", "settings.local.json"):
        f = target / ".claude" / fname
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for block in data.get("hooks", {}).get(event, []):
            for h in block.get("hooks", []):
                cmd = h.get("command")
                if cmd:
                    cmds.append(cmd)
    return cmds


def run_hook(cmd, target, timeout=HOOK_TIMEOUT):
    """Live run of one SessionStart-hook: empty stdin, timeout, fail-soft.
    additionalContext from hookSpecificOutput JSON, otherwise raw stdout (same
    contract that he reads himself Claude Code). Returns (tokens, ok); ok=False on
    any failure/timeout/non-zero exit — this is the report DATA (hook of someone else's project
    may be broken), is not a reason for the team itself to fall."""
    run_env = dict(os.environ)
    run_env["CLAUDE_PROJECT_DIR"] = str(target)
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=str(target), env=run_env, input="",
            capture_output=True, text=True, timeout=timeout, check=False)
    except Exception:
        return None, False
    if result.returncode != 0:
        return None, False
    out = result.stdout.strip()
    if not out:
        return 0, True
    ctx = out
    try:
        data = json.loads(out)
        ctx = data.get("hookSpecificOutput", {}).get("additionalContext", out)
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return estimate_tokens(ctx), True


def measure_hooks(target, timeout=HOOK_TIMEOUT, provider=DEFAULT_LISTING_PROVIDER, run_hooks=True):
    """Price of the SessionStart hooks of ``target``. The hooks are shell commands of that project: with
    ``run_hooks=False`` they are counted but not run (the tokens are then unknown, ``None``)."""
    if provider != "claude-code":
        return {"tokens": 0,
                "detail": f"no measurable SessionStart-contract for {provider}"}
    cmds = settings_hook_commands(target, "SessionStart")
    if not cmds:
        return {"tokens": 0, "detail": "no SessionStart-hooks"}
    if not run_hooks:
        return {"tokens": None,
                "detail": f"n/a ({len(cmds)} SessionStart hook(s) of another project not run; --run-hooks runs them)"}
    total, ok_n, fail_n = 0, 0, 0
    for cmd in cmds:
        tokens, ok = run_hook(cmd, target, timeout=timeout)
        if ok:
            total += tokens
            ok_n += 1
        else:
            fail_n += 1
    if ok_n == 0:
        return {"tokens": None, "detail": f"n/a ({fail_n} hook(ov) failed)"}
    detail = f"{ok_n} hook(ov)" + (f", {fail_n} n/a" if fail_n else "")
    return {"tokens": total, "detail": detail}


def measure_mcp(target, *, host_servers=None):
    """Mode-dependent resident price estimation MCP-project servers (.mcp.json,
    P2.3/D19/D22): `mode`/`mode_source` — NEW keys (additivity D16), not
    change `tokens`/`detail` in form. Three branches:
      off      — old age model (tool count × TOKENS_PER_MCP_TOOL),
                 is honest only when ENABLE_TOOL_SEARCH=false;
      auto     — assumption «within 10% context window» NOT verified
                 alive /context (not available to agent) → take the same ager-
                 ceiling as an explicitly named upper bound (Implementation
                 Rules P2.3 §3, Scope Included «auto — with explicitly named
                 assumption»);
      deferred — client default: tool names (TOKENS_PER_MCP_TOOL_NAME)
                 + server instructions (actually measured for servers with
                 local source, otherwise FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS)
                 — lower bound.
    We do not parse real schemas (server may not be accessible from this environment)
    — this is an assessment, like the whole budget.py.

    ``host_servers`` maps a server name to an object with ``tools`` and ``instructions_tokens``
    attributes (the host-owned data of the caller); ``None`` means no host data."""
    f = Path(target) / ".mcp.json"
    if not f.is_file():
        return {"tokens": 0, "detail": "no .mcp.json", "mode": None,
                "mode_source": None, "estimate_class": None}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"tokens": None, "detail": "n/a (.mcp.json invalid JSON)",
                "mode": None, "mode_source": None, "estimate_class": None}
    servers = sorted(data.get("mcpServers", {}))
    mode, source = tool_search_mode(target)
    if not servers:
        return {"tokens": 0, "detail": "no servers", "mode": mode,
                "mode_source": source, "estimate_class": None}
    host_servers = host_servers or {}
    if mode == MCP_MODE_OFF:
        total = sum(mcp_tool_count(n, host_servers) * TOKENS_PER_MCP_TOOL
                   for n in servers)
        est_class = "accurate model of complete circuits (ENABLE_TOOL_SEARCH=false)"
    elif mode == MCP_MODE_AUTO:
        total = sum(mcp_tool_count(n, host_servers) * TOKENS_PER_MCP_TOOL
                   for n in servers)
        est_class = ("upper limit (auto: assumption «within 10% windows» "
                     "not verified live /context)")
    else:
        total = 0
        for n in servers:
            total += mcp_tool_count(n, host_servers) * TOKENS_PER_MCP_TOOL_NAME
            total += mcp_instruction_tokens(n, host_servers)
        est_class = "lower bound (deferred: tool names + server instructions)"
    return {"tokens": total, "detail": f"{len(servers)} server(ov): " + ", ".join(servers),
           "mode": mode, "mode_source": source, "estimate_class": est_class}


FIRST_TURN_SOURCE_LABELS = (
    ("skills", "skills meta (⊕ always)"),
    ("agents", ".claude/agents"),
    ("claude_md", "CLAUDE.md + rules"),
    ("hooks", "SessionStart-hooks (live run)"),
    ("mcp", "MCP tool-defs"),
)


def first_turn_verdict(total):
    """Three-pronged verdict OK/ELEVATED/WARN by thresholds FIRST_TURN_TARGET_MAX/
    FIRST_TURN_WARN — the only carrier of the ladder (is also used for
    project `total`, and for plugin-inclusive `session_total`, D16)."""
    if total <= FIRST_TURN_TARGET_MAX:
        return "OK"
    elif total <= FIRST_TURN_WARN:
        return "ELEVATED"
    return "WARN"


def codex_integrity(report):
    """Return native-discovery drift that invalidates a strict Codex receipt."""
    skills = report["sources"]["skills"]
    issues = []
    if skills.get("duplicates"):
        issues.append("SKILL_DUPLICATE_NAME")
    if skills.get("enabled_outside_project_policy"):
        issues.append("CODEX_PLUGIN_ENABLED_OUTSIDE_PROJECT_POLICY")
    if skills.get("desired_plugins_not_effective"):
        issues.append("CODEX_DESIRED_PLUGIN_NOT_EFFECTIVE")
    return {"status": "clean" if not issues else "degraded", "issues": issues}


def format_plugins_block(plugins):
    """Summary block always-on marketplace-plugins (--with-plugins, D16 —
    is called ONLY when the key `plugins` is already in the report, otherwise the output will not
    changes completely)."""
    out = ["  Marketplace-plugins (always-on)"]
    if plugins["status"] != "ok":
        out.append(f"    n/a — {'; '.join(plugins['warnings']) or 'listing not available'}")
        return out
    if not plugins["entries"]:
        out.append("    no enabled-plugins")
    for e in plugins["entries"]:
        tok_str = "   n/a" if e["tokens"] is None else f"{e['tokens']:>6}"
        out.append(f"    {e['id']} ({e['scope']})".ljust(30) + f" {tok_str} current")
    if plugins["broken"]:
        broken_str = "; ".join(f"{b['id']} ({b['reason']})" for b in plugins["broken"])
        out.append(f"    broken: {broken_str}")
    if plugins["unparsed"]:
        out.append(f"    unparsed: {'; '.join(plugins['unparsed'])}")
    if plugins["warnings"]:
        out.append(f"    warnings: {'; '.join(plugins['warnings'])}")
    out.append(f"    Total plugins: {'n/a' if plugins['total'] is None else plugins['total']} current"
               + ("  (partial)" if plugins["partial"] else ""))
    return out


def format_first_turn_report(report):
    out = ["", "━━━ FIRST-TURN BUDGET ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
          f"Project: {report['target']}",
          f"Provider: {report.get('provider', 'claude-code')}", ""]
    for key, label in FIRST_TURN_SOURCE_LABELS:
        s = report["sources"].get(key, {})
        if key == "claude_md":
            label = s.get("surface", label)
        elif key == "agents" and report.get("provider") == "codex":
            label = "provider agents"
        tok = s.get("tokens")
        tok_str = "   n/a" if tok is None else f"{tok:>6}"
        out.append(f"  {label:<28} {tok_str} current  ({s.get('detail', '')})")
        raw = s.get("raw_tokens")
        if raw is not None and raw != tok:
            out.append(f"  {'  (sum of descriptions to budget)':<28} {raw:>6} current")
        if key == "skills" and s.get("excluded"):
            # P3.2: record captured by the native field is not included in the resident - number
            # is published as a separate line (DEVICE effect, not registry diet).
            out.append(f"  {'  ' + format_listing_exclusions(s['excluded_by']):<28} "
                       f"{-s['excluded_raw']:>6} current out of listing")
        if key == "skills" and s.get("managed_tokens") is not None:
            out.append(f"  {'  managed estimate':<28} {s['managed_tokens']:>6} current")
        if key == "skills" and s.get("duplicates"):
            names = ", ".join(row["name"] for row in s["duplicates"])
            out.append(f"  {'  duplicate names':<28} {names}")
        if key == "skills" and s.get("enabled_outside_project_policy"):
            names = ", ".join(s["enabled_outside_project_policy"])
            out.append(f"  {'  plugins outside policy':<28} {names}")
        if key == "skills" and s.get("desired_plugins_not_effective"):
            names = ", ".join(s["desired_plugins_not_effective"])
            out.append(f"  {'  missing policy plugins':<28} {names}")
        if key == "mcp" and s.get("mode"):
            out.append(f"  {'  tool search':<28} {s['mode']} "
                       f"(source: {s['mode_source']}) — {s['estimate_class']}")
    if "plugins" in report:
        out.append("")
        out.extend(format_plugins_block(report["plugins"]))
    out.append("")
    out.append(f"Total: {report['total']:>6} current — {report['verdict']}  "
               f"(target ≤{FIRST_TURN_TARGET_MAX} · warn >{FIRST_TURN_WARN})")
    if "session_total" in report:
        out.append(f"Total with plugins: {report['session_total']:>6} current — "
                   f"{report['session_verdict']}")
    out.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append("")
    return "\n".join(out)


# --- text report ------------------------------------------------------------
def bar(value, scale):
    return "█" * min(40, round(value / scale)) if scale else ""


def format_report(label, b):
    """Human-readable three-tier report on the result budget_for_set."""
    out = []
    pct = b["if_all_triggered"] / CONTEXT_LIMIT * 100
    out.append("")
    out.append("━━━ TOKEN BUDGET ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append(f"Set:        {label}")
    out.append(f"Skills:      {b['count']}  "
               f"(transitive via requires: {b['transitive']})")
    out.append(f"⊕ always:     {b['tier0']:>6} current - resident EVERY request "
               f"(name+description)")
    out.append(f"↻ on-trigger: {b['tier1']:>6} current - bodies, if ALL work")
    out.append(f"⌥ on-demand:  {b['tier2']:>6} current - snippets/references, upon request")
    out.append(f"Σ if everything:   {b['if_all_triggered']:>6} current  "
               f"(~{pct:.1f}% from {CONTEXT_LIMIT // 1000}K)")

    by_b = b["by_bucket"]
    if by_b:
        out.append("")
        out.append("─── By buckets (⊕ always / ↻ bodies / skills) ─────────")
        for bucket in sorted(by_b, key=lambda k: by_b[k]["tier0"], reverse=True):
            a = by_b[bucket]
            out.append(f"  {bucket:<22} ⊕{a['tier0']:>5}  ↻{a['tier1']:>6}  "
                       f"({a['count']})")

    top0 = sorted(b["items"], key=lambda i: i["tier0"], reverse=True)[:TOP_N]
    if top0:
        scale = max(i["tier0"] for i in top0) / 20 or 1
        width = max(len(f"{i['bucket']}/{i['name']}") for i in top0)
        out.append("")
        out.append("─── Top descriptions (⊕ always — permanent tax) ─────────")
        for i in top0:
            tag = " [transitive]" if i["transitive"] else ""
            label = f"{i['bucket']}/{i['name']}".ljust(width)
            out.append(f"  {label} {i['tier0']:>5} current  "
                       f"{bar(i['tier0'], scale)}{tag}")

    top1 = sorted(b["items"], key=lambda i: i["tier1"], reverse=True)[:TOP_N]
    if top1:
        width = max(len(f"{i['bucket']}/{i['name']}") for i in top1)
        out.append("")
        out.append("─── Top Bodies (↻ on-trigger — trigger price) ────────")
        for i in top1:
            label = f"{i['bucket']}/{i['name']}".ljust(width)
            out.append(f"  {label} {i['tier1']:>5} current")
    out.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append("")
    return "\n".join(out)
