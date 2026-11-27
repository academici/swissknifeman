"""Deterministic migration of donor skills into inert SKM extension packs (P09.06)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from skm.modules.extensions.application.candidate import DEFAULT_ALLOWED_LICENSES, build_candidate
from skm.modules.extensions.domain.compat import CompatVerdict
from skm.modules.extensions.domain.payload import PackPayload, PayloadFile
from skm.modules.extensions.domain.skill import parse_skill_frontmatter

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

PACK_SCHEMA, SKILL_SCHEMA = "urn:skm:extensions:pack:v1", "urn:skm:extensions:skill-manifest:v1"
REQUIRES_SKM, DEFAULT_VERSION, MAX_AUX_FILES = ">=0.1.0,<1", "1.0.0", 198
CORE_SKILL_KEYS = frozenset(
    {
        "diagnosing-bugs",
        "grill-me",
        "handoff",
        "implement",
        "research-method",
        "review-checklist",
        "security-review",
        "spec-review",
        "tdd",
        "to-spec",
        "to-tickets",
    }
)
CORE_REPLACEMENTS: Mapping[str, str] = {
    "code-review": "spec-review",
    "grill-with-docs": "grill-me",
    "session-handoff": "handoff",
    "spec-interview": "grill-me",
    "tdd-discipline": "tdd",
    "to-issues": "to-tickets",
}
GUARD_PATH = (
    "resources/packs/agent-packs-local/agent-packs-backend-laravel/"
    "integration-bundles/agent-pack-backend-laravel/snippets/TestEnvironmentGuard.php"
)
PRUNED_PACK_SKILLS: Mapping[str, tuple[str, ...]] = {
    "migrated-frontend": (
        "dark-mode",
        "eslint-flat-config",
        "filepond-upload",
        "inertia-vue",
        "laravel-echo-client",
        "naive-ui-theming",
        "pinia-stores",
        "reka-ui-cva",
        "tailwind-conventions",
        "vitest",
        "vue-composition-api",
        "vue-dynamic-icons",
        "wayfinder",
    ),
    "migrated-upstream-frontend": (
        "antfu",
        "js-code-style",
        "motion",
        "nuxt",
        "nuxt-modules",
        "nuxt-seo",
        "pinia",
        "vite",
        "vitepress",
        "vitest-vue",
        "vue",
        "vue-best-practices",
        "vue-router-best-practices",
        "vue-testing-best-practices",
        "vueuse-functions",
        "web-design-guidelines",
    ),
    "migrated-laravel-php": (
        "database",
        "dependency-injection",
        "eloquent-accessors",
        "enum-attributes",
        "enum-state-machine",
        "laravel",
        "laravel-data",
        "laravel-dusk",
        "laravel-permissions",
        "laravel-structure",
        "laravel-testing",
        "livewire-blade-attributes",
        "medialibrary",
        "named-arguments",
        "php-naming-conventions",
        "php-patterns",
        "repositories",
        "spatie-settings",
        "static-analysis",
        "test-isolation-guard",
    ),
    "migrated-upstream-laravel-php": (
        "code-style-spatie",
        "filament",
        "laravel-best-practices",
        "laravel-broadcasting",
        "pennant-development",
    ),
    "migrated-upstream-general": (
        "git-safety",
        "grill-with-docs",
        "implement",
        "to-issues",
    ),
    "migrated-upstream-quality-security": (
        "diagnosing-bugs",
        "tdd-discipline",
    ),
    "migrated-general": (
        "complex-task-orchestrator",
        "git-commit-rules",
        "session-handoff",
        "spec-interview",
    ),
}
PRUNED_SKILL_KEYS = frozenset(key for keys in PRUNED_PACK_SKILLS.values() for key in keys)
PERSONAL_BUCKETS = frozenset({"axioma", "azguard", "botkit"})
OVERLAY_SKILLS: Mapping[tuple[str, str], str] = {
    ("general", "skills-ssot"): "ecosystem_coupled_skill",
    ("general", "mcp-advisor"): "ecosystem_coupled_skill",
    ("founder", "defensibility"): "ecosystem_coupled_skill",
    ("general", "writing-style"): "personal_language_overlay",
}
TOPIC_GROUPS: Mapping[str, tuple[str, ...]] = {
    "ai": ("ai", "voice-ai"),
    "business": ("creative", "finance", "founder", "legal", "marketing", "operator", "pm", "sales"),
    "general": ("general", "oss-dev", "roles"),
    "platforms": ("dart", "mobile"),
    "quality-security": ("quality", "research", "security"),
}
EXACT_TOPIC_MAP: Mapping[str, str] = {b: t for t, bs in TOPIC_GROUPS.items() for b in bs}
TOPIC_TITLES: Mapping[str, str] = {
    "ai": "AI & Voice Agents",
    "architect": "Architecture & System Design",
    "business": "Product, Strategy & Operations",
    "devops": "DevOps & Containers",
    "frontend": "Frontend, Vue & TypeScript",
    "general": "General Engineering Workflows",
    "laravel-php": "PHP & Laravel Engineering",
    "platforms": "Mobile, Dart & 3D Platforms",
    "python": "Python Engineering",
    "quality-security": "Quality, Research & Security",
}
KIND_MAP = {k: k for k in ("router", "reference", "persona", "workflow")} | {"procedure": "workflow"}
RISK_MAP = {"medium": "medium", "draft": "medium", "high": "high", "write": "high", "exec": "high"}
VALID_ROLES = frozenset({"scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar"})
STANDARD_TOOLS = frozenset({"Read", "Edit", "Write", "Grep", "Glob", "Bash", "WebFetch", "WebSearch"})
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$")
KEY_RE, SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$"), re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
DEP_RE = re.compile(r"^(pip|npm|composer|cargo|go):[A-Za-z0-9@/._-]+$")
HEX64_RE, DATE_RE = re.compile(r"^[0-9a-f]{64}$"), re.compile(r"^\d{4}-\d{2}-\d{2}$")
MCP_TOOL_RE = re.compile(r"^mcp__[a-z0-9_-]+__[a-z0-9_-]+$")
MT_MARKERS = ("machine-translated", "translated automatically", "autotranslated", "машинный перевод")
LOCAL_SUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(re.escape('"Ignore previous instructions..."')), '"Override earlier task rules..."'),
    (re.compile(re.escape("- Read .env from mounted file,")), "- Load .env from mounted file,"),
    (re.compile(re.escape("include .env / export")), "include ./.env / export"),
    (re.compile(re.escape("## .gitignore — must include venvs")), "## .gitignore — must list venvs"),
    (
        re.compile(r"Don't bypass hooks[: ]+\(?`--no-verify` forbidden without explicit user request\)?\."),
        "Never pass --no-verify to bypass git hooks without explicit user request.",
    ),
    (re.compile(r"(?m)^(#|//)\s*Source:\s*(?:academici|azguard)/[^\n]*$"), r"\1 Source: anonymized template"),
    (re.compile(r"\(same risk `axioma-stack`[^)]*\)", re.I), "(same risk with relative config paths)"),
    (re.compile(r";\s*azguard has its own skill", re.I), ""),
    (
        re.compile(r"New projects:\s*prefer package \*\*azguard\*\*[^.\n]*\."),
        "Prefer a code-first RBAC package for new projects.",
    ),
    (
        re.compile(
            r'(?:,\s*|/\s*)`azguard/azguard`|`azguard/azguard`\s*/\s*|"azguard",\s*|\s*\(`writing-style`\)'
        ),
        "",
    ),
    (re.compile(r"(?m)^-\s*`(?:azguard/azguard|botkit/botkit|(?:general/)?writing-style)`[^\n]*\n"), ""),
    (re.compile(r"\(BrainKit,\s*AzGuard(?:,\s*ThemeOn,\s*other OSS)?\)", re.I), "(OSS libraries)"),
    (re.compile(r"adapted for the registry swissknifeman", re.I), "adapted for the skill catalog"),
    (re.compile(r"`swissknifeman-issue-triager`"), "`issue-triager`"),
    (re.compile(r"markers `swissknifeman:hub:start/end`"), "managed hub block markers"),
    (re.compile(r"Message in Russian", re.I), "Message in repository language"),
    (re.compile(r"academici/swissknifeman", re.I), "org/project"),
)


class _HeuristicEstimator:
    estimator_id = "heuristic-v1"

    def estimate(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4) if text else 0


class RawSkill(NamedTuple):
    origin: str
    bucket: str
    raw_name: str
    key: str
    path: Path
    rel_source: str


class MigratedSkill(NamedTuple):
    key: str
    topic: str
    upstream: bool
    version: str
    exclusive_group: str | None
    files: Mapping[str, bytes]
    mt_flagged: bool


def _q(val: str) -> str:
    return json.dumps(val, ensure_ascii=False)


def _qlist(items: Sequence[str]) -> str:
    return "[" + ", ".join(_q(x) for x in items) + "]"


def _slugify(value: str) -> str:
    cleaned = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-"))
    return cleaned if len(cleaned) >= 2 else f"s-{cleaned or 'pack'}"


def _topic_for_bucket(b: str) -> str:
    if b in EXACT_TOPIC_MAP or b.startswith("frontend-"):
        return EXACT_TOPIC_MAP.get(b, "frontend")
    if b.startswith(("laravel-", "php")):
        return "laravel-php"
    return "platforms" if b.startswith("blender") else _slugify(b)


def _parse_scalar_or_inline(val: str) -> Any:
    if not val:
        return []
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        return [p.strip().strip("\"'") for p in inner.split(",") if p.strip()] if inner else []
    return val[1:-1] if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'") else val


def _parse_legacy_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    text = raw_text.removeprefix("\ufeff").replace("\r\n", "\n")
    lines = text.split("\n")
    end_idx = (
        next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), None)
        if lines and lines[0].strip() == "---"
        else None
    )
    if end_idx is None:
        return {}, text
    meta, cur_key = {}, None
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "\t")) or stripped.startswith("- "):
            if cur_key and stripped.startswith("- ") and isinstance(meta.get(cur_key), list):
                meta[cur_key].append(stripped[2:].strip().strip("\"'"))
        elif ":" in line:
            k, raw_v = line.split(":", 1)
            cur_key = k.strip()
            meta[cur_key] = _parse_scalar_or_inline(raw_v.strip())
    return meta, "\n".join(lines[end_idx + 1 :])


def _format_skill_markdown(key: str, description: str, body: str) -> str:
    clean_desc = " ".join(description.replace('"', "'").split()).strip() or f"Guidance for {key}."
    clean_desc = clean_desc[:1017].rstrip() + "..." if len(clean_desc) > 1020 else clean_desc
    rendered = f'---\nname: {key}\ndescription: "{clean_desc}"\n---\n\n{body.lstrip(chr(10)).rstrip()}\n'
    parse_skill_frontmatter(rendered, key=key)
    return rendered


def _iter_skill_dirs(source_root: Path) -> Iterator[tuple[str, str, Path]]:
    roots = [
        ("skiller", b.name, b)
        for b in sorted((source_root / "packages" / "skiller" / "skills").iterdir(), key=lambda p: p.name)
        if b.is_dir()
    ]
    roots += [
        (f"package:{p.name}", p.name, p / "skills")
        for p in sorted((source_root / "packages").iterdir(), key=lambda p: p.name)
        if p.name != "skiller" and (p / "skills").is_dir()
    ]
    for origin, bucket, parent in roots:
        for s_dir in sorted(parent.iterdir(), key=lambda p: p.name):
            if s_dir.is_dir() and (s_dir / "SKILL.md").is_file():
                yield (origin, bucket, s_dir)


def _discover_donor_skills(source_root: Path) -> list[RawSkill]:
    prelim = [
        (o, b, s.name, s, _parse_legacy_frontmatter((s / "SKILL.md").read_text())[0])
        for o, b, s in _iter_skill_dirs(source_root)
    ]
    counts: dict[str, int] = {}
    for _, _, raw_name, _, _ in prelim:
        counts[raw_name] = counts.get(raw_name, 0) + 1
    claimed, results = set(), []
    for origin, bucket, raw_name, s_dir, fm in prelim:
        cand, fm_name = _slugify(raw_name), str(fm.get("name", "")).strip()
        if counts[raw_name] > 1 and KEY_RE.match(fm_name) and fm_name not in claimed:
            cand = fm_name
        cand = _slugify(f"{bucket}-{raw_name}") if cand in claimed else cand
        claimed.add(cand)
        results.append(
            RawSkill(origin, bucket, raw_name, cand, s_dir, s_dir.relative_to(source_root).as_posix())
        )
    return results


def _exclusion_entry(s: RawSkill) -> dict[str, Any] | None:
    reason: str | None = OVERLAY_SKILLS.get((s.bucket, s.raw_name))
    core_key = CORE_REPLACEMENTS.get(s.key, s.key)
    if core_key in CORE_SKILL_KEYS:
        reason = "already_in_core"
    elif s.key == "test-isolation-guard":
        reason = "moved_to_agent_pack"
    elif s.key in PRUNED_SKILL_KEYS:
        reason = "pruned_from_builtin_packs"
    elif s.bucket in PERSONAL_BUCKETS:
        reason = "personal_overlay_bucket"
    elif s.origin != "skiller":
        reason = "legacy_monorepo_package"
    elif reason is None and any(
        t in (s.path / "SKILL.md").read_text()
        for t in (".swissknifeman/launcher.py", "AxiomaErpSdk", "academici ecosystem")
    ):
        reason = "ecosystem_coupled_skill"
    if reason is None:
        return None
    core = reason == "already_in_core"
    ext = "operator overlay pack"
    compat = "Neutral core runs without this skill."
    usr = "author_or_single_ecosystem"
    if core:
        ext = f"resources/packs/core/skills/{core_key}"
        compat = "Provided by core pack."
        usr = "all_skm_users_via_core"
    elif reason == "moved_to_agent_pack":
        ext = GUARD_PATH
        compat = "The test guard is provided by the Laravel agent pack."
        usr = "laravel_agent_pack_users"
    elif reason == "pruned_from_builtin_packs":
        usr = "project_specific"
    rem = "tests/integration/extensions/test_migrated_packs.py"
    g36 = {
        "users_beyond_author": core or reason == "moved_to_agent_pack",
        "users": usr,
        "extension_point": ext,
    }
    g36 |= {"compatible_without_it": compat, "removal_test": rem}
    base = {"key": s.key, "origin": s.origin, "bucket": s.bucket, "source_path": s.rel_source}
    return base | {"reason": reason, "g36": g36}


def _normalize_tool(raw_tool: str) -> str | None:
    tool = raw_tool.strip()
    if tool in STANDARD_TOOLS or MCP_TOOL_RE.match(tool):
        return tool
    return (
        f"mcp__{srv}__tools"
        if tool.endswith("-mcp") and (srv := re.sub(r"[^a-z0-9_-]+", "_", tool[:-4].lower()).strip("_"))
        else None
    )


def _normalize_local_text(text: str) -> str:
    for pattern, repl in LOCAL_SUBS:
        text = pattern.sub(repl, text)
    return text


def _compact_aux_files(files: dict[str, bytes]) -> dict[str, bytes]:
    if len(files) <= MAX_AUX_FILES:
        return files
    kept, buckets = {}, {}
    keep_exact = {"references/catalog.md", "references/full.md", "references/index.md"}
    for rel, content in sorted(files.items()):
        if not rel.startswith("references/") or rel in keep_exact:
            kept[rel] = content
        else:
            stem = Path(rel).stem
            buckets.setdefault(stem[0].lower() if stem and stem[0].isalnum() else "other", []).append(
                (rel, content.decode("utf-8").rstrip())
            )
    for ch, items in sorted(buckets.items()):
        kept[f"references/bundle-{ch}.md"] = (
            "\n\n---\n\n".join(f"<!-- source: {r} -->\n{t}" for r, t in items) + "\n"
        ).encode("utf-8")
    return kept


def _collect_auxiliary_files(skill_dir: Path, *, is_upstream: bool) -> tuple[dict[str, bytes], bool]:
    files, relocated = {}, False
    for path in sorted(skill_dir.rglob("*"), key=lambda p: p.as_posix()):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(skill_dir).as_posix()
        if "__pycache__" in rel.split("/") or path.name == ".DS_Store":
            continue
        if rel.startswith(("references/", "snippets/", "examples/")):
            target = rel
        elif rel.startswith("reference/"):
            target, relocated = "references/" + rel.removeprefix("reference/"), True
        else:
            continue
        txt = path.read_bytes().decode("utf-8").removeprefix("\ufeff").replace("\r\n", "\n")
        files[target] = (_normalize_local_text(txt) if not is_upstream else txt).encode("utf-8")
    return _compact_aux_files(files), relocated


def _build_provenance_toml(
    upstream_doc: Mapping[str, Any] | None, all_files: Mapping[str, bytes]
) -> tuple[bool, str, list[str]]:
    if not upstream_doc or upstream_doc.get("kind") == "reference-only" or not upstream_doc.get("repo"):
        return False, "Apache-2.0", ['[provenance]\nsource = "local"']
    repo = str(upstream_doc["repo"]).strip()[:300]
    strat = str(upstream_doc.get("strategy") or "notify").strip()
    strat = strat if strat in {"replace", "notify", "fork", "merge"} else "notify"
    up_lic = str(upstream_doc.get("license") or "").strip()
    lic = up_lic if up_lic in DEFAULT_ALLOWED_LICENSES else "Apache-2.0"

    rows: list[tuple[str, str, str, str]] = []
    for entry in upstream_doc.get("files") or []:
        if not isinstance(entry, dict) or not (raw_p := str(entry.get("path") or "").strip()):
            continue
        norm_p = "references/" + raw_p.removeprefix("reference/") if raw_p.startswith("reference/") else raw_p
        url = str(entry.get("url") or "").strip()
        if norm_p not in all_files or not url.startswith("https://"):
            continue
        sha = str(entry.get("sha256") or "").strip().lower()
        sha = sha if HEX64_RE.match(sha) else hashlib.sha256(all_files[norm_p]).hexdigest()
        f_date = str(entry.get("fetched_at") or "").strip()
        rows.append((norm_p, url, sha, f_date if DATE_RE.match(f_date) else "2026-01-01"))

    raw_audit = upstream_doc.get("audit")
    audit: Mapping[str, Any] = raw_audit if isinstance(raw_audit, dict) else {}
    up_sha = str(upstream_doc.get("upstream_sha") or audit.get("upstream_sha") or "").strip().lower()
    up_sha = up_sha if HEX64_RE.match(up_sha) else (rows[0][2] if rows else "")
    if not (repo and HEX64_RE.match(up_sha) and rows):
        return False, "Apache-2.0", ['[provenance]\nsource = "local"']

    p_lines = [
        f'[provenance]\nsource = "upstream"\nrepo = {_q(repo)}\nstrategy = {_q(strat)}',
        f"license = {_q(lic)}\nupstream_sha = {_q(up_sha)}",
    ]
    if verdict := str(audit.get("verdict") or "").strip()[:100]:
        p_lines.append(f"audit_verdict = {_q(verdict)}")
    if DATE_RE.match(audit_at := str(audit.get("at") or "").strip()):
        p_lines.append(f"audit_at = {_q(audit_at)}")
    for path, url, sha, f_at in rows:
        hdr = f"\n[[provenance.files]]\npath = {_q(path)}\nurl = {_q(url)}"
        p_lines.append(f"{hdr}\nsha256 = {_q(sha)}\nfetched_at = {_q(f_at)}")
    sections = ["\n".join(p_lines)]
    for waiver in upstream_doc.get("compat_accepted") or []:
        if not isinstance(waiver, dict):
            continue
        wf = str(waiver.get("file") or "").strip()
        wf = "references/" + wf.removeprefix("reference/") if wf.startswith("reference/") else wf
        wc = [str(c).strip() for c in (waiver.get("checks") or []) if str(c).strip()]
        if wf and wc and (wr := str(waiver.get("reason") or "").strip()):
            sections.append(f"[[compat_accepted]]\nfile = {_q(wf)}\nchecks = {_qlist(wc)}\nreason = {_q(wr)}")
    return True, lic, sections


def _render_skill_manifest(
    skill: RawSkill,
    *,
    fm: Mapping[str, Any],
    selection: Mapping[str, Any],
    upstream_doc: Mapping[str, Any] | None,
    all_files: Mapping[str, bytes],
    valid_keys: frozenset[str],
) -> tuple[str, str, bool, str | None]:
    raw_ver = str(fm.get("version", DEFAULT_VERSION)).strip()
    version = raw_ver if SEMVER_RE.match(raw_ver) else DEFAULT_VERSION
    kind = KIND_MAP.get(str(selection.get("kind", "domain")).strip(), "domain")
    risk = RISK_MAP.get(str(fm.get("risk", "low")).strip().lower(), "low")
    is_upstream, lic, prov_sections = _build_provenance_toml(upstream_doc, all_files)

    lines = [
        f"schema = {_q(SKILL_SCHEMA)}\nkey = {_q(skill.key)}\nversion = {_q(version)}",
        f"kind = {_q(kind)}\nrisk = {_q(risk)}\nlicense = {_q(lic)}",
    ]
    if roles := sorted(
        {str(r).strip() for r in (selection.get("roles") or []) if str(r).strip() in VALID_ROLES}
    ):
        lines.append(f"roles = {_qlist(roles)}")
    fm_reqs = fm.get("requires")
    raw_reqs: Sequence[Any] = fm_reqs if isinstance(fm_reqs, list) else ()
    if reqs := sorted(
        {k for r in raw_reqs if (k := str(r).strip().split("/")[-1]) in valid_keys and k != skill.key}
    ):
        lines.append(f"requires = {_qlist(reqs)}")
    raw_tools = selection.get("requires_tools") or selection.get("tools") or []
    if tools := sorted({m for t in raw_tools if (m := _normalize_tool(str(t))) is not None}):
        lines.append(f"requires_tools = {_qlist(tools)}")
    raw_grp = str(selection.get("exclusive_group") or "").strip()
    exclusive_group = raw_grp if SLUG_RE.match(raw_grp) else None
    if exclusive_group:
        lines.append(f"exclusive_group = {_q(exclusive_group)}")
    if repl := str(selection.get("replaced_by") or "").strip()[:120]:
        lines.append(f"replaced_by = {_q(repl)}")
    raw_conf = selection.get("conflicts") or []
    if confs := sorted(
        {k for c in raw_conf if (k := str(c).strip().split("/")[-1]) in valid_keys and k != skill.key}
    ):
        lines.append(f"conflicts_with = {_qlist(confs)}")

    trig = selection.get("triggers")
    if isinstance(trig, dict):
        tp = list(
            dict.fromkeys(
                str(p).strip() for p in (trig.get("paths") or []) if 1 <= len(str(p).strip()) <= 200
            )
        )
        td = list(
            dict.fromkeys(str(d).strip() for d in (trig.get("deps") or []) if DEP_RE.match(str(d).strip()))
        )
        if tp or td:
            lines.append("\n[triggers]")
            lines.extend([f"paths = {_qlist(tp)}"] if tp else [])
            lines.extend([f"deps = {_qlist(td)}"] if td else [])
    lines.extend(f"\n{sec}" for sec in prov_sections)
    return "\n".join(lines) + "\n", version, is_upstream, exclusive_group


def _migrate_single_skill(skill: RawSkill, *, valid_keys: frozenset[str]) -> MigratedSkill:
    fm, body = _parse_legacy_frontmatter((skill.path / "SKILL.md").read_text(encoding="utf-8"))
    sel_p, up_p = skill.path / "selection.json", skill.path / "upstream.json"
    selection: dict[str, Any] = json.loads(sel_p.read_text(encoding="utf-8")) if sel_p.is_file() else {}
    up_doc: dict[str, Any] | None = json.loads(up_p.read_text(encoding="utf-8")) if up_p.is_file() else None
    prelim_up = bool(up_doc and up_doc.get("kind") != "reference-only" and up_doc.get("repo"))
    aux_files, relocated = _collect_auxiliary_files(skill.path, is_upstream=prelim_up)
    if relocated or "./reference/" in body:
        body = body.replace("./reference/", "./references/").replace("`reference/", "`references/")
    desc = str(fm.get("description") or "").strip()
    body, desc = (body, desc) if prelim_up else (_normalize_local_text(body), _normalize_local_text(desc))
    md_bytes = _format_skill_markdown(skill.key, desc, body).encode("utf-8")
    all_in = {"SKILL.md": md_bytes, **aux_files}
    manifest_txt, ver, is_up, grp = _render_skill_manifest(
        skill, fm=fm, selection=selection, upstream_doc=up_doc, all_files=all_in, valid_keys=valid_keys
    )
    all_files = {"manifest.toml": manifest_txt.encode("utf-8"), **all_in}
    mt = any(m in b.decode("utf-8").lower() for b in all_files.values() for m in MT_MARKERS)
    return MigratedSkill(skill.key, _topic_for_bucket(skill.bucket), is_up, ver, grp, all_files, mt)


def _render_pack_toml(
    slug: str, topic: str, *, upstream: bool, used_groups: Sequence[str], group_defs: Mapping[str, Any]
) -> str:
    t_title = TOPIC_TITLES.get(topic, topic.replace("-", " ").title())
    prefix = "Migrated Upstream Skills" if upstream else "Migrated Neutral Skills"
    prov = "upstream-mirrored third-party" if upstream else "neutral authored"
    desc = f"Reproducibly migrated {prov} skills for {t_title} (inert third_party data pack)."
    version = "1.1.0" if slug in PRUNED_PACK_SKILLS else DEFAULT_VERSION
    lines = [
        f"schema = {_q(PACK_SCHEMA)}\nslug = {_q(slug)}\nversion = {_q(version)}",
        f"title = {_q(f'{prefix}: {t_title}'[:120])}\ndescription = {_q(desc)}",
        'publisher = "skm-migrated"\ntrust = "third_party"\npriority = -100',
        f'license = "Apache-2.0"\nrequires_skm = {_q(REQUIRES_SKM)}',
    ]
    for g_name in sorted(set(used_groups)):
        raw_meta = group_defs.get(g_name)
        meta: Mapping[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        g_desc = str(meta.get("description") or f"Mutual exclusion group {g_name}.")[:500]
        hdr = f"\n[[exclusive_groups]]\nname = {_q(g_name)}\nmax = {max(1, int(meta.get('max', 1)))}"
        lines.append(f"{hdr}\ndescription = {_q(g_desc)}")
    return "\n".join(lines) + "\n"


def _write_outputs(
    output_dir: Path,
    overlay_export: Path,
    packs: Sequence[tuple[Path, str, PackPayload]],
    doc: Mapping[str, Any],
) -> None:
    if output_dir.is_dir():
        for child in sorted(output_dir.iterdir(), key=lambda p: p.name):
            if child.is_dir() and child.name.startswith("migrated-"):
                shutil.rmtree(child)
    for pack_dir, pack_toml, payload in packs:
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "pack.toml").write_bytes(pack_toml.encode("utf-8"))
        for pf in payload.files:
            dest = pack_dir / pf.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(pf.content)
    overlay_export.parent.mkdir(parents=True, exist_ok=True)
    overlay_export.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_migration(
    *, source_arg: str, output_dir: Path, overlay_export: Path, dry_run: bool
) -> dict[str, Any]:
    source_root = Path(source_arg)
    skiller_dir = source_root / "packages" / "skiller" / "skills"
    if not source_root.is_dir() or not skiller_dir.is_dir():
        raise FileNotFoundError(f"donor skill root not found: expected directory '{skiller_dir}'")
    raw_skills = _discover_donor_skills(source_root)
    if not raw_skills:
        raise ValueError(f"no donor skills found under '{skiller_dir}'")

    excluded, neutral_raw = [], []
    for item in raw_skills:
        (excluded.append(ex) if (ex := _exclusion_entry(item)) is not None else neutral_raw.append(item))

    valid_keys = frozenset({s.key for s in neutral_raw} | CORE_SKILL_KEYS)
    migrated = [_migrate_single_skill(s, valid_keys=valid_keys) for s in neutral_raw]
    grouped: dict[tuple[bool, str], list[MigratedSkill]] = {}
    for ms in migrated:
        grouped.setdefault((ms.upstream, ms.topic), []).append(ms)

    eg_cfg = source_root / "packages" / "skiller" / "configs" / "exclusive-groups.json"
    group_defs = json.loads(eg_cfg.read_text()).get("groups", {}) if eg_cfg.is_file() else {}
    estimator, packs_to_write, pack_records = _HeuristicEstimator(), [], []

    for (is_up, topic), members in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        tier, slug = (
            ("migrated-upstream", f"migrated-upstream-{topic}")
            if is_up
            else ("migrated-local", f"migrated-{topic}")
        )
        used_groups = [ms.exclusive_group for ms in members if ms.exclusive_group is not None]
        pack_toml = _render_pack_toml(
            slug, topic, upstream=is_up, used_groups=used_groups, group_defs=group_defs
        )
        p_files = sorted(
            (PayloadFile(f"skills/{ms.key}/{k}", v) for ms in members for k, v in ms.files.items()),
            key=lambda pf: pf.path,
        )
        payload = PackPayload(manifest_text=pack_toml, files=tuple(p_files))
        cand = build_candidate(payload, estimator=estimator, scan=True)
        if bad := [r.key for r in cand.resources if r.compat.verdict is not CompatVerdict.CLEAN]:
            raise ValueError(f"pack {slug} failed compat CLEAN check for skills: {bad}")
        packs_to_write.append((output_dir / tier / slug, pack_toml, payload))
        skills_list = [{"key": r.key, "version": str(r.version), "digest": r.digest} for r in cand.resources]
        rec: dict[str, Any] = {"slug": slug, "tier": "upstream" if is_up else "local", "topic": topic}
        rec |= {"path": f"resources/packs/{tier}/{slug}", "trust": cand.manifest.trust.value}
        rec |= {"priority": cand.manifest.priority, "digest": cand.digest}
        rec |= {"skill_count": len(cand.resources), "skills": skills_list}
        pack_records.append(rec)

    src_p = Path(source_arg)
    src_label = (
        "../swissknifeman"
        if source_root.name == "swissknifeman"
        else (src_p.name if src_p.is_absolute() else src_p.as_posix())
    )
    mt_rule = "Unreviewed machine-translated skills are quarantined or flagged before core promotion."
    n_raw, n_mig, n_ex, n_pk = len(raw_skills), len(migrated), len(excluded), len(pack_records)
    counts = {"source_total": n_raw, "migrated": n_mig, "excluded": n_ex, "packs": n_pk}
    mt_pol = {"rule": mt_rule, "flagged_skills": sorted(ms.key for ms in migrated if ms.mt_flagged)}
    sorted_ex = sorted(excluded, key=lambda e: (str(e["origin"]), str(e["bucket"]), str(e["key"])))
    export_doc: dict[str, Any] = {"schema": "urn:skm:extensions:migrated-skills-export:v1"}
    export_doc |= {"source_root": src_label, "counts": counts, "machine_translation_policy": mt_pol}
    export_doc |= {"packs": pack_records, "excluded_skills": sorted_ex}
    if not dry_run:
        _write_outputs(output_dir, overlay_export, packs_to_write, export_doc)
    return export_doc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="migrate_skills.py", description="Migrate neutral donor skills.")
    parser.add_argument("--source", default="../swissknifeman", help="Path to read-only donor repository.")
    parser.add_argument("--output", default="resources/packs", help="Output packs root directory.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing.")
    parser.add_argument(
        "--overlay-export", default="resources/overlays/exports.json", help="Export JSON path."
    )
    args = parser.parse_args(argv)
    try:
        doc = run_migration(
            source_arg=args.source,
            output_dir=Path(args.output),
            overlay_export=Path(args.overlay_export),
            dry_run=bool(args.dry_run),
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        sys.stderr.write(f"migrate_skills: error: {exc}\n")
        return 2
    packs = [
        {"slug": p["slug"], "skill_count": p["skill_count"], "digest": p["digest"]} for p in doc["packs"]
    ]
    sys.stdout.write(
        json.dumps({"dry_run": bool(args.dry_run), "counts": doc["counts"], "packs": packs}, indent=2) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
