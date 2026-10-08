"""budget — token budget for skill set (three-tier disclosure model).

Why: the set of skills is inflated silently. This is visible only if you distinguish WHAT
is always loaded, but what about conditionally:

  tier-0 ⊕ always     — name+description of each active skill. Resident in
                        EVERY request (based on them the agent decides whether to use the skill).
                        This is the permanent «tax» — main metric.
  tier-1 ↻ on-trigger — body SKILL.md. Loads only when the skill is triggered.
  tier-2 ⌥ on-demand  — snippets and references. Loaded via a link from the body,
                        optional (references — bodies of monoliths after
                        thin-navigator-waves, see P2.1 SKM-MASTER-003).

Token scoring is ROUGH and language dependent (Cyrillic is denser than Latin
tokenizer Claude), stdlib-only, without third-party tokenizers. That's why
EN-canon is cheaper RU with equal volume - this is a visible translation gain. Number
is suitable for COMPARING sets and relative weights, not for accurate counting. Source of mathematics ONE (`aicore.content.budget`; this module composes it with skiller selection) — use it CLI
(`skiller budget`), map generator (docs/guide/budget.md) and the line in
`skiller status`."""
import json
import os
from pathlib import Path

from core import atomic_write_text

from aicore.content.skill import split_frontmatter as _split_frontmatter  # noqa: F401 (re-export)
from aicore.content.budget import (  # noqa: F401 (re-export under the historical names)
    CHARS_PER_TOKEN_CYR,
    CHARS_PER_TOKEN_LAT,
    CONTEXT_LIMIT,
    TOP_N,
    estimate_tokens,
    skill_budget,
    budget_for_set,
    FIRST_TURN_TARGET_MAX,
    FIRST_TURN_WARN,
    HOOK_TIMEOUT,
    KNOWN_MCP_TOOLS,
    FALLBACK_MCP_TOOLS,
    TOKENS_PER_MCP_TOOL,
    ENABLE_TOOL_SEARCH_ENV,
    MCP_MODE_DEFERRED,
    MCP_MODE_AUTO,
    MCP_MODE_OFF,
    MCP_MODE_SOURCE_DEFAULT,
    TOKENS_PER_MCP_TOOL_NAME,
    FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS,
    mcp_tool_count as _mcp_tool_count,
    mcp_instruction_tokens as _mcp_instruction_tokens,
    tool_search_mode as _tool_search_mode,
    SKILL_LISTING_MAX_ENTRY_CHARS,
    SKILL_LISTING_BUDGET_FRACTION,
    SKILL_LISTING_CONTEXT_WINDOW,
    CODEX_LISTING_FALLBACK_CHARS,
    CODEX_LISTING_BUDGET_FRACTION,
    LISTING_PROVIDERS,
    CHAR_LISTING_PROVIDERS as _CHAR_LISTING_PROVIDERS,
    DEFAULT_LISTING_PROVIDER,
    MEASUREMENT_SURFACES,
    MEASUREMENT_CLASSES,
    MEASUREMENT_STATUSES,
    MEASUREMENT_TTL,
    LISTING_EXCLUDED_BY_FIELDS,
    LISTING_EXCLUSION_PROVIDERS,
    listing_exclusion as _listing_exclusion,
    split_listing_entries as _split_listing_entries,
    format_listing_exclusions,
    listing_entry_tokens as _listing_entry_tokens,
    listing_entry_chars as _listing_entry_chars,
    measure_listing_budget,
    measurement_timestamp as _measurement_timestamp,
    measurement_number as _measurement_number,
    make_measurement,
    aggregate_measurements,
    listing_measurements,
    format_listing_report,
    measure_agents as _measure_agents,
    measure_claude_md as _measure_claude_md,
    measure_instructions as _measure_instructions,
    settings_hook_commands as _settings_hook_commands,
    run_hook as _run_hook,
    measure_hooks as _measure_hooks,
    measure_mcp,
    FIRST_TURN_SOURCE_LABELS as _FIRST_TURN_SOURCE_LABELS,
    first_turn_verdict as _first_turn_verdict,
    codex_integrity as _codex_integrity,
    format_plugins_block as _format_plugins_block,
    format_first_turn_report,
    bar as _bar,
    format_report,
)

from .common import die, parse_flags, parse_frontmatter
from .config import (CORE_SKILLS, DEFAULT_EXCLUDE, RESIDENT_BUDGET_TARGET,
                     ProjectConfig, all_buckets, core_skill_tuples, default_command_plugins,
                     known_command_plugins,
                     find_project_root, load_config, resolve_selection,
                     validate_config)
from .host import load_host
from .plugins import plugins_summary
from .native_codex import native_inventory
from .vendor import build_requires_index, collect_skills, resolve_requires


# --- active set (how I would assemble vendor, without installation) ----------------------
def resolve_active_set(env, target, config, *, profile="", flag_buckets=None,
                       flag_exclude=None, no_core=False):
    """Active set of project skills, without writing to disk. Reuses
    resolve_selection / collect_skills / core_skill_tuples / resolve_requires —
    same selection as `skiller vendor`. Returns (skills, meta), where
    skills — [(bucket, rel, dir, fm_name)], meta['pulled'] — transitive deps."""
    config = ProjectConfig.coerce(config)  # historical calls are sent dict
    flag_buckets = flag_buckets or []
    flag_exclude = flag_exclude or []
    buckets, profile_name, _profile_source, source, _include_meta = \
        resolve_selection(env, target, config, profile, flag_buckets)
    known = all_buckets(env)
    for b in buckets:
        if b not in known and b not in known_command_plugins():
            die(f"unknown bucket: {b}")
    buckets = [b for b in buckets if b in known]
    exclude = set(flag_exclude) | set(config.exclude)
    if not no_core:
        exclude |= set(DEFAULT_EXCLUDE)
    skills, _ = collect_skills(env, buckets, exclude)
    core_added = []
    if not no_core:
        have = {f"{b}/{r}" for b, r, _, _ in skills}
        for tup in core_skill_tuples(env, exclude):
            if f"{tup[0]}/{tup[1]}" not in have:
                skills.append(tup)
                core_added.append(f"{tup[0]}/{tup[1]}")
    index = build_requires_index(env)
    dependency_diagnostics = []
    pulled = resolve_requires(
        skills, index, exclude, diagnostics=dependency_diagnostics)
    meta = {"buckets": list(buckets), "profile": profile_name, "source": source,
            "exclude": sorted(exclude), "pulled": pulled, "core_added": core_added,
            "dependency_diagnostics": dependency_diagnostics}
    return skills, meta

def _host_mcp_servers():
    """Host `mcp_servers` (tools / instructions_tokens) of this Skiller install."""
    return load_host(Path(__file__).resolve().parents[2]).mcp_servers

def _measure_mcp(target):
    """MCP price of the project servers, with the host ``mcp_servers`` of this install."""
    return measure_mcp(target, host_servers=_host_mcp_servers())

def profiles_listing_report(env):
    """Detection budget for EACH profile delivered (`profiles/*.json`) against BOTH
    providers - metering mode `--profiles` (P3.4 Scope Included). Same production
    path that distribution connect-channel (`resolve_active_set` + supervised `core@`)."""
    rows = []
    for name in sorted(p.stem for p in (env.root / "profiles").glob("*.json")):
        skills, _meta = resolve_active_set(env, env.root, {}, profile=name)
        rows.append({
            "profile": name, "count": len(skills),
            "codex": measure_listing_budget(skills, "codex"),
            "claude-code": measure_listing_budget(skills, "claude-code"),
        })
    return rows


def format_profiles_listing_report(rows):
    out = ["", "━━━ DETECTION BUDGET BY PROFILE (provider-aware, P3.4) ━━━━━━━━━━━━━━━",
          "", "| Profile | Skills | Codex (char) | vs fallback 8000 | Claude Code (current) "
          "| vs budget 1% @1M |", "|:--|--:|--:|:--|--:|:--|"]
    for r in rows:
        c, k = r["codex"], r["claude-code"]
        out.append(f"| {r['profile']} | {r['count']} | {c['raw']} | "
                   f"{'BREAKTHROUGH' if c['over'] else 'ok'} | {k['raw']} | "
                   f"{'BREAKTHROUGH' if k['over'] else 'ok'} |")
    out.append("")
    return "\n".join(out)


def _managed_skill_measurement(env, target, provider, *,
                               listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                               listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Listing resident of the project's active skill set - budget model
    above (cap to write + ceiling = context_window*fraction), not the sum of all
    descriptions (that re-discount was the reason D22/[POSSIBLE-DEFECT] in intelligence P3.4).
    n/a for any failure (unfamiliar bucket in someone else's .swissknife.json etc.) — not
    should drop the entire report."""
    try:
        config = load_config(env, target)
        skills, meta = resolve_active_set(env, target, config)
        all_dirs = [d for _bucket, _rel, d, _fm in skills]
        dirs, excluded = _split_listing_entries(all_dirs, provider)
        raw = sum(_listing_entry_tokens(d) for d in dirs)
        budget = int(listing_context_window * listing_fraction)
        resident = min(raw, budget)
        detail = f"{len(skills)} skills"
        if excluded:
            detail += f", in the listing {len(dirs)}"
        if raw > budget:
            detail += (f", listing {raw} > budget {budget} current → resident "
                      f"{resident} (client drops rarely called descriptions)")
        return {"tokens": resident, "raw_tokens": raw, "listing_budget": budget,
                "desired_plugins": list(config.plugins),
                "excluded": sum(len(ds) for ds in excluded.values()),
                "excluded_by": {f: len(ds) for f, ds in sorted(excluded.items())},
                "excluded_raw": sum(_listing_entry_tokens(d)
                                    for ds in excluded.values() for d in ds),
                "detail": detail}
    except (Exception, SystemExit) as e:
        return {"tokens": None, "detail": f"n/a ({e})"}


def _measure_skills(env, target, *, provider=DEFAULT_LISTING_PROVIDER,
                    listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                    listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Use provider-observed skill inventory when the provider exposes it."""
    managed = _managed_skill_measurement(
        env, target, provider,
        listing_fraction=listing_fraction,
        listing_context_window=listing_context_window)
    if provider != "codex":
        managed["measurement"] = "managed-estimate"
        return managed

    observed = native_inventory(env, target)
    managed_fields = {
        "managed_tokens": managed.get("tokens"),
        "managed_raw_tokens": managed.get("raw_tokens"),
        "managed_detail": managed.get("detail"),
        "desired_plugins": managed.get("desired_plugins", []),
    }
    if not observed["ok"]:
        return {
            **managed_fields,
            "tokens": None,
            "detail": "; ".join(observed["notes"]),
            "measurement": "provider-unavailable",
            "observed_count": None,
            "enabled_plugins": observed.get("enabled", []),
            "duplicates": [],
        }

    entries = []
    for name, paths in sorted(observed["paths"].items()):
        for raw_path in paths:
            path = Path(raw_path)
            tokens = None
            try:
                fm = parse_frontmatter(path)
                tokens = estimate_tokens(
                    f"{fm.get('name', name) or name} {fm.get('description', '')}")
            except (OSError, ValueError, TypeError):
                pass
            entries.append({"name": name, "path": raw_path, "tokens": tokens})
    missing = [entry for entry in entries if entry["tokens"] is None]
    duplicates = [
        {"name": name, "paths": list(paths)}
        for name, paths in sorted(observed["paths"].items()) if len(paths) > 1
    ]
    total = None if missing else sum(entry["tokens"] for entry in entries)
    desired = set(managed.get("desired_plugins", [])) - set(default_command_plugins())
    outside_policy = sorted(set(observed["enabled"]) - desired) if desired else []
    not_effective = sorted(desired - set(observed["enabled"]))
    return {
        **managed_fields,
        "tokens": total,
        "raw_tokens": total,
        "detail": (f"Codex observed: {len(entries)} entries / "
                   f"{len(observed['names'])} unique names; managed: "
                   f"{managed.get('detail', 'n/a')}")
                  + (f"; {len(missing)} unreadable" if missing else ""),
        "measurement": "provider-observed" if total is not None else "provider-partial",
        "observed_count": len(entries),
        "observed_unique_names": len(observed["names"]),
        "enabled_plugins": observed["enabled"],
        "enabled_outside_project_policy": outside_policy,
        "desired_plugins_not_effective": not_effective,
        "duplicates": duplicates,
    }

def first_turn_report(env, target, *, provider=DEFAULT_LISTING_PROVIDER,
                      timeout=HOOK_TIMEOUT,
                      listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                      listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Amount always-on footprint of the first progress of the project based on five sources.
    n/a-sources (fail-soft) are not included in the amount - total only counts what
    what is actually measured. Verdict: OK ≤16K · ELEVATED ≤23K · WARN >23K
    (thresholds - FIRST_TURN_TARGET_MAX/FIRST_TURN_WARN, justification there:
    baseline fleet,
    D83). `listing_fraction`/
    `listing_context_window` — skill listing budget share and context window
    target model; parameters, not constants (P3.4 Implementation Rules —
    hard-coated default will go bad when changing `skillListingBudgetFraction`)."""
    target = Path(target).resolve()
    sources = {
        "skills": _measure_skills(env, target, provider=provider,
                                  listing_fraction=listing_fraction,
                                  listing_context_window=listing_context_window),
        "agents": _measure_agents(target, provider=provider),
        "claude_md": _measure_instructions(target, provider=provider),
        "hooks": _measure_hooks(target, timeout=timeout, provider=provider),
        "mcp": _measure_mcp(target),
    }
    total = sum(s["tokens"] for s in sources.values() if s["tokens"] is not None)
    complete = all(source["tokens"] is not None for source in sources.values())
    report = {"target": str(target), "sources": sources, "total": total,
              "verdict": _first_turn_verdict(total) if complete else "INCOMPLETE"}
    if provider != DEFAULT_LISTING_PROVIDER:
        report["provider"] = provider
        report["measurement_status"] = "complete" if complete else "incomplete"
        report["scope"] = "managed-first-turn"
        report["platform_overhead"] = "excluded"
        if provider == "codex":
            report["integrity"] = _codex_integrity(report)
    return report

# --- permission of configs for CLI ----------------------------------------------
def _load_config_file(env, path):
    p = Path(os.path.expanduser(path))
    if not p.is_file():
        die(f"config not found: {p}")
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{p}: invalid JSON: {e}")
    validate_config(env, cfg, str(p))
    return cfg, p.resolve().parent


def _config_by_name(env, name):
    """Name from --compare → budget-configs/<name>.json (or path if available)."""
    cand = Path(os.path.expanduser(name))
    if cand.suffix == ".json" and cand.is_file():
        return _load_config_file(env, str(cand))
    return _load_config_file(env, str(env.root / "budget-configs" / f"{name}.json"))


def _budget_from_config(env, config, target, no_core):
    skills, meta = resolve_active_set(env, target, config, no_core=no_core)
    return budget_for_set(skills, meta["pulled"])


# --- CLI ----------------------------------------------------------------------
def cmd_budget(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--config": "str", "--compare": "str",
        "--profile": "str", "--buckets": "str", "--exclude": "str",
        "--json": "bool", "--no-core": "bool", "--write-map": "bool",
        "--check-core": "bool", "--strict": "bool", "--first-turn": "bool",
        "--provider": "str", "--profiles": "bool", "--with-plugins": "bool",
    })
    if opts["help"]:
        print("skiller budget [--config F.json | --compare a,b | --target DIR]\n"
              "               [--profile P | --buckets a,b] [--exclude x,y]\n"
              "               [--provider claude-code|codex|cursor|grok] [--profiles]\n"
              "               [--no-core] [--json] [--write-map] [--check-core [--strict]]\n"
              "               [--first-turn [--provider claude-code|codex|cursor|grok] "
              "[--json] [--strict]]\n"
              "  Three-tier token budget for skill sets (⊕ always / ↻ on-trigger\n"
              "  / ⌥ on-demand). --write-map will regenerate docs/guide/budget.md.\n"
              "  --check-core: resident (⊕ tier-0) budget CORE_SKILLS vs target (gate\n"
              "  against the quiet growth of the core And against the quiet shortage - missing along the way\n"
              "  CORE-the skill is reduced by the resident, rather than improved); --strict — non-zero\n"
              "  code when exceeding OR undershooting (CI).\n"
              "  --first-turn: provider-aware always-on footprint of the first progress of the project.\n"
              "  Claude measures CLAUDE.md/rules, agents and SessionStart; Codex — AGENTS.md\n"
              "  and actual native prompt inventory with duplicate/policy diagnostics;\n"
              "  target ≤16K / warn >23K current; --strict — exit 1 when WARN/INCOMPLETE\n"
              "  or Codex duplicate/policy drift (CI).\n"
              "  --with-plugins (only together with --first-turn): adds always-on price\n"
              "  installed marketplace-project plugins (`claude plugin list/details`)\n"
              "  additive keys `plugins`/`session_total`/`session_verdict` — without\n"
              "  flag does not change the output.\n"
              "  --provider claude-code|codex|cursor|grok (with --profile/--config/--target): adds to\n"
              "  report provider-aware detection budget (listing) and degradation mode;\n"
              "  without the flag the behavior does not change (default — claude-code).\n"
              "  --profiles: detection budget for EACH supplied profile versus BOTH\n"
              "  providers (P3.4).")
        return
    no_core = opts.get("no_core", False)
    if opts.get("with_plugins") and not opts.get("first_turn"):
        die("--with-plugins requires --first-turn")

    if opts.get("write_map"):
        write_budget_map(env)
        return

    if opts.get("profiles"):
        rows = profiles_listing_report(env)
        if opts.get("json"):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print(format_profiles_listing_report(rows))
        return

    if opts.get("first_turn"):
        if opts.get("target"):
            target = Path(os.path.expanduser(opts["target"])).resolve()
        else:
            target, _via = find_project_root(env)
            if target is None:
                die("project root not found above CWD — specify --target")
        provider = opts.get("provider") or DEFAULT_LISTING_PROVIDER
        if provider not in LISTING_PROVIDERS:
            die("--provider: expected " + "|".join(LISTING_PROVIDERS))
        report = first_turn_report(env, target, provider=provider)
        if opts.get("with_plugins"):
            if provider != "claude-code":
                die("--with-plugins currently only measures Claude Code; for Codex use "
                    "provider-observed inventory without this flag")
            plugins = plugins_summary(target)
            report["plugins"] = plugins
            session_total = (report["total"] if plugins["total"] is None
                            else report["total"] + plugins["total"])
            report["session_total"] = session_total
            report["session_verdict"] = _first_turn_verdict(session_total)
        if opts.get("json"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_first_turn_report(report))
        integrity = report.get("integrity", {})
        if opts.get("strict") and (report["verdict"] in {"WARN", "INCOMPLETE"}
                                    or integrity.get("issues")):
            details = ", ".join(integrity.get("issues", ()))
            die(f"first-turn budget {report['total']} current > warn-threshold "
                f"{FIRST_TURN_WARN}, measurement incomplete or native inventory drift"
                f"{': ' + details if details else ''} ({target}) — see table above")
        return

    if opts.get("check_core"):
        tuples = core_skill_tuples(env, set())
        cards = [skill_budget(d) for (_b, _rel, d, _n) in tuples]
        cards = [c for c in cards if c]
        # core_skill_tuples/skill_budget silently skip CORE_SKILLS-path without SKILL.md
        # (moving/typo) — previously the missing skill was simply reduced resident and did
        # gate «greener» (audit B-2). Shortfall is a separate error, not «lucky with the budget».
        missing = len(CORE_SKILLS) - len(cards)
        resident = sum(c["tier0"] for c in cards)
        over = resident > RESIDENT_BUDGET_TARGET
        status = "MISSING" if missing else ("OVER" if over else "OK")
        if opts.get("json"):
            print(json.dumps({"resident_core_tier0": resident,
                              "target": RESIDENT_BUDGET_TARGET,
                              "skills": len(cards), "expected_skills": len(CORE_SKILLS),
                              "missing": missing, "status": status},
                             ensure_ascii=False))
        else:
            print(f"CORE resident (⊕ tier-0): {resident} current / target "
                  f"{RESIDENT_BUDGET_TARGET} — {status} "
                  f"({len(cards)}/{len(CORE_SKILLS)} skills)")
        if missing and opts.get("strict"):
            die(f"CORE shortfall: {missing} from {len(CORE_SKILLS)} CORE_SKILLS not found "
                f"on disk (moving/path typo in config.py/core-policy.json) — "
                f"resident is understated, not improved")
        if over and opts.get("strict"):
            die(f"CORE resident budget {resident} > target "
                f"{RESIDENT_BUDGET_TARGET}: squeeze description or review the composition CORE")
        return

    if opts.get("compare"):
        names = [n for n in opts["compare"].split(",") if n]
        if len(names) < 2:
            die("--compare is waiting ≥2 config separated by commas: --compare a,b")
        results = []
        for name in names:
            cfg, tdir = _config_by_name(env, name)
            results.append((name, _budget_from_config(env, cfg, tdir, no_core)))
        if opts.get("json"):
            print(json.dumps({n: b for n, b in results}, indent=2,
                             ensure_ascii=False))
            return
        print("\n━━━ SET COMPARISON ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for name, b in results:
            print(f"  {name:<26} ⊕{b['tier0']:>5}  ↻{b['tier1']:>6}  "
                  f"Σ{b['if_all_triggered']:>6}  ({b['count']} skills)")
        worst = max(results, key=lambda r: r[1]["if_all_triggered"])
        print(f"  The hardest: {worst[0]}\n")
        for name, b in results:
            print(format_report(name, b))
        return

    # single set: --config | .swissknife.json from --target/CWD
    flag_buckets = [b for b in opts.get("buckets", "").split(",") if b]
    flag_exclude = [e for e in opts.get("exclude", "").split(",") if e]
    if opts.get("config"):
        config, target = _load_config_file(env, opts["config"])
        label = opts["config"]
    else:
        if opts.get("target"):
            target = Path(os.path.expanduser(opts["target"])).resolve()
        else:
            target, _via = find_project_root(env)
            if target is None:
                die("project root not found above CWD — specify --config or --target")
        config = load_config(env, target)
        label = str(target)
    skills, meta = resolve_active_set(
        env, target, config, profile=opts.get("profile", ""),
        flag_buckets=flag_buckets, flag_exclude=flag_exclude, no_core=no_core)
    b = budget_for_set(skills, meta["pulled"])
    listing = (measure_listing_budget(skills, opts["provider"])
              if opts.get("provider") else None)
    if opts.get("json"):
        out = {"label": label, "meta": {
            "buckets": meta["buckets"], "profile": meta["profile"],
            "source": meta["source"]}, **b}
        if listing is not None:
            out["listing"] = listing
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print(format_report(f"{label}  [profile: {meta['profile'] or '-'} "
                        f"via {meta['source']}]", b))
    if listing is not None:
        print(format_listing_report(listing))


# --- map generator docs/guide/budget.md -------------------------------------
def _docs_root(p):
    """Nearest up directory with docs/guide (package itself; fallback — p)."""
    for cand in (p, *p.parents):
        if (cand / "docs" / "guide").is_dir():
            return cand
    return p


def _node_id(name):
    return name.replace("-", "_").replace("/", "_")


def _quantile(values, frac):
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * frac))]


def render_budget_map(root, registry):
    """Text docs/guide/budget.md (without entry) from registry-dict — mermaid-map
    three-tier budget + tables by buckets/tops. Reads bodies SKILL.md by
    registry-paths relative to root. Removed from write_budget_map, to
    registry.check_drift could check the relevance without a side entry (R-2:
    earlier only write-path existed, drift-gate did not see this artifact).
    Returns (text, n_skills, total0, total1)."""
    rows = []
    for e in registry["skills"]:
        b = skill_budget((root / e["path"]).parent)
        if b is None:
            continue
        rows.append({"name": e["name"], "bucket": e["bucket"],
                     "tier0": b["tier0"], "tier1": b["tier1"],
                     "tier2": b["tier2"], "snippets": b["snippets"],
                     "references": b["references"],
                     "requires": e.get("requires", [])})

    by_name = {r["name"]: r for r in rows}
    # heat by distribution ⊕ always (quantiles - robust to selection CHARS_PER_TOKEN)
    t0_vals = [r["tier0"] for r in rows]
    q_hot, q_warm, q_mild = (_quantile(t0_vals, 0.85), _quantile(t0_vals, 0.6),
                             _quantile(t0_vals, 0.3))

    def heat(t0):
        if t0 >= q_hot:
            return "hot"
        if t0 >= q_warm:
            return "warm"
        if t0 >= q_mild:
            return "mild"
        return "cool"

    by_bucket = {}
    for r in rows:
        by_bucket.setdefault(r["bucket"], []).append(r)

    total0 = sum(r["tier0"] for r in rows)
    total1 = sum(r["tier1"] for r in rows)
    total2 = sum(r["tier2"] for r in rows)

    lines = [
        "# Token Budget Map",
        "",
        "> Generated `lib/skiller/budget.py` (`skiller budget --write-map`) "
        "from `skills.json` and tel. `SKILL.md` — cannot be edited manually.",
        "> Reassembly: `skiller registry`.",
        "",
        "Three-tier context disclosure model - what loads the neural network and when:",
        "",
        "- **⊕ always** — `name`+`description`: are resident in EVERY request "
        "(based on them the agent decides whether to use the skill). Permanent «tax».",
        "- **↻ on-trigger** — body `SKILL.md`: is loaded only when the skill is triggered.",
        "- **⌥ on-demand** — snippets and references: via link from the body, optional.",
        "",
        "Node color - heat by **⊕ always** (redder = more expensive permanent tax "
        "descriptions). Label `name<br/>⊕always ↻body`. Solid arrow `requires` "
        "shows a transitive tax: you put a skill - you pull always-price "
        "dependencies. Token valuation is rough and language dependent (Cyrillic "
        f"~{CHARS_PER_TOKEN_CYR:g} chars/tok, Latin/code ~{CHARS_PER_TOKEN_LAT:g}) "
        "— for comparison of sets, not exact accounting.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for bucket in sorted(by_bucket):
        lines.append(f"  subgraph {_node_id(bucket)}[\"{bucket}\"]")
        for r in sorted(by_bucket[bucket], key=lambda x: x["name"]):
            label = f"{r['name']}<br/>⊕{r['tier0']} ↻{r['tier1']}"
            lines.append(f"    {_node_id(r['name'])}[\"{label}\"]:::{heat(r['tier0'])}")
        lines.append("  end")
    # ribs requires — only when both ends are on the card
    edges = sorted({(r["name"], dep) for r in rows for dep in r["requires"]
                    if dep in by_name})
    for src, dst in edges:
        lines.append(f"  {_node_id(src)} -->|requires| {_node_id(dst)}")
    lines += [
        "  classDef hot fill:#c0392b,color:#fff,stroke:#7b241c;",
        "  classDef warm fill:#e67e22,color:#fff,stroke:#a04000;",
        "  classDef mild fill:#f1c40f,color:#222,stroke:#b7950b;",
        "  classDef cool fill:#27ae60,color:#fff,stroke:#1e8449;",
        "```",
        "",
        f"**Total:** {len(rows)} skills · ⊕ always **{total0}** current "
        f"(is always resident if you include the entire registry) · ↻ bodies {total1} current "
        f"· ⌥ on-demand {total2} current (snippets + references).",
        "",
        "## By buckets",
        "",
        "| Bucket | Skills | ⊕ always | ↻ bodies | ⌥ on-demand |",
        "|---|--:|--:|--:|--:|",
    ]
    for bucket in sorted(by_bucket, key=lambda k: sum(
            r["tier0"] for r in by_bucket[k]), reverse=True):
        rs = by_bucket[bucket]
        lines.append(f"| `{bucket}` | {len(rs)} | {sum(r['tier0'] for r in rs)} "
                     f"| {sum(r['tier1'] for r in rs)} "
                     f"| {sum(r['tier2'] for r in rs)} |")

    def _top_table(title, key, note):
        out = ["", f"## {title}", "", note, "",
               "| Skill | Bucket | current |", "|---|---|--:|"]
        for r in sorted(rows, key=lambda x: x[key], reverse=True)[:TOP_N]:
            out.append(f"| `{r['name']}` | {r['bucket']} | {r[key]} |")
        return out

    lines += _top_table("Top ⊕ always (permanent tax)", "tier0",
                        "The most expensive descriptions are resident in each request.")
    lines += _top_table("Top ↻ on-trigger (trigger price)", "tier1",
                        "The heaviest bodies are loaded when using the skill.")
    lines.append("")
    return "\n".join(lines), len(rows), total0, total1


def write_budget_map(env):
    """Generate docs/guide/budget.md (atomically) from skills.json on disk."""
    root = env.root
    reg_file = root / "skills.json"
    if not reg_file.is_file():
        die("skills.json not found - run first `skiller registry`")
    registry = json.loads(reg_file.read_text(encoding="utf-8"))
    text, n_skills, total0, total1 = render_budget_map(root, registry)
    out = _docs_root(root) / "docs" / "guide" / "budget.md"
    atomic_write_text(out, text)
    print(f"Updated {out.relative_to(_docs_root(root))}: {n_skills} skills, "
          f"⊕{total0} ↻{total1} current")
