#!/usr/bin/env bash
# Validate repository structure: SKILL.md frontmatter, upstream.json,
# profiles/*.json, skills.json, snippet manifests.
# Used locally and by .github/workflows/validate.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- aicore locator ---
# Finds the aicore foundation: $AICORE_ROOT, then <module>/_vendor/aicore, then the sibling <module>/../aicore.
# Canonical copy: packages/aicore/scripts/aicore-locator.sh; copies must stay identical.
_aicore_ok() { [ -f "$1/unit.json" ] && grep -q '"id": *"aicore"' "$1/unit.json"; }
if [ -n "${AICORE_ROOT:-}" ]; then
  _aicore_ok "$AICORE_ROOT" || { echo "AICORE_NOT_FOUND: AICORE_ROOT=$AICORE_ROOT is not an aicore checkout" >&2; exit 2; }
elif _aicore_ok "$REPO_ROOT/_vendor/aicore"; then
  AICORE_ROOT="$REPO_ROOT/_vendor/aicore"
elif _aicore_ok "$REPO_ROOT/../aicore"; then
  AICORE_ROOT="$(cd "$REPO_ROOT/../aicore" && pwd)"
else
  echo "AICORE_NOT_FOUND: no aicore in \$AICORE_ROOT, $REPO_ROOT/_vendor/aicore or $REPO_ROOT/../aicore; set AICORE_ROOT" >&2
  exit 2
fi
export AICORE_ROOT
AICORE_LIB="$AICORE_ROOT/lib"
unset -f _aicore_ok
# --- end aicore locator ---

# The first Python block imports skiller.host, which needs `core` and, through it, `aicore`.
export PYTHONPATH="$AICORE_LIB${PYTHONPATH:+:$PYTHONPATH}"

# P4.2: the generate-skill snippet is a generated projection of the EN canonical
# template. Keep this as integration-only composition: ownership of both predicates
# stays in their dedicated scripts. Isolated legacy validator fixtures intentionally
# copy only this script, so they retain their narrower checks without a false failure.
if [ -f "$REPO_ROOT/scripts/generate-skill-template.py" ] && [ -f "$REPO_ROOT/scripts/check-translations.sh" ]; then
  python3 "$REPO_ROOT/scripts/generate-skill-template.py" --check
  bash "$REPO_ROOT/scripts/check-translations.sh" --strict
fi

python3 - "$REPO_ROOT" <<'PY'
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])  # package root (skills/, lib/, buckets.json)
# marketplace.json — in root monorepo; source-plugin paths are relative to the repo root.
# (Canon - aicore.util.repo.find_repo_root; here is a self-contained take: the heredoc
#  does not import the package on purpose.)
def _repo_root(p):
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    return p
repo_root = _repo_root(root)
errors = []
warnings = []

# --- CLAUDE.md line-count (token-saving; WARN, not fail) ------------------
# CLAUDE.md is resident EVERY session (Anthropic target ≤200 lines). Soft gate
# monorepo: root + packages/*/CLAUDE.md. Root — umbrella guide, can grow legitimately →
# hold warning, is not a block.
CLAUDE_MD_MAX_LINES = 200
for _cmd_md in [repo_root / "CLAUDE.md", *sorted((repo_root / "packages").glob("*/CLAUDE.md"))]:
    if _cmd_md.is_file():
        _n = len(_cmd_md.read_text(encoding="utf-8", errors="replace").splitlines())
        if _n > CLAUDE_MD_MAX_LINES:
            warnings.append(f"{_cmd_md.relative_to(repo_root)}: {_n} lines "
                            f"(> {CLAUDE_MD_MAX_LINES}) — CLAUDE.md is resident every session, "
                            "put the details in docs/skills (token-saving)")

# --- core-policy.json (declarative CORE-policy, source config.py) --------
_core_policy_path = root / "configs" / "core-policy.json"
if _core_policy_path.is_file():
    try:
        _cp = json.loads(_core_policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as _e:
        errors.append(f"configs/core-policy.json: invalid JSON: {_e}")
        _cp = None
    if isinstance(_cp, dict):
        for _sk in _cp.get("skills", []):
            if not (root / "skills" / _sk / "SKILL.md").is_file():
                errors.append(f"core-policy.json skills[]: '{_sk}' — no skills/{_sk}/SKILL.md")
        for _ex in _cp.get("default_exclude", []):
            if not (root / "skills" / _ex / "SKILL.md").is_file():
                warnings.append(f"core-policy.json default_exclude[]: '{_ex}' — "
                                f"no skills/{_ex}/SKILL.md")
else:
    warnings.append("configs/core-policy.json missing - config.py on built-in fallback")

UPSTREAM_SOURCES = {"github", "http", "file"}
# replace = mirror (autoroll); notify = adapted copy (report only);
# fork = fork with our changes (wrapper + pristine-mirror in files[].path; on the drift
#        review_pending=true blocks distribution - manual transfer, then --resolve);
# merge = composite of ≥2 external sources (origins[]: base + supplement/«suggest»),
#        collected into a single skill; sync MANUAL under agent control (on the drift of any
#        origin merge.review_pending=true blocks - the agent re-merges, then --resolve).
UPSTREAM_STRATEGIES = {"replace", "notify", "fork", "merge"}
# Roles of sources in composite-skill (strategy=merge): base — is taken as a basis;
# supplement — complementary source-«suggest» (what is merged from it - into note/suggest).
ORIGIN_ROLES = {"base", "supplement"}
# P5.11 (thread (B) OQ-6): human verdict on the bundle - machine readable record
# next to the skill, not a row in the table inside the plan. verdict — what I saw
# read; kind distinguishes a bundle that does not vendor ANYTHING (all files[].path
# are empty - provenance-LINKS to external specs), from vendor: denominator
# «N vendor bundles» is otherwise heterogeneous, and the verdict anchor for such a bundle
# is meaningless by design. See docs/guide/vendored-skills.md.
AUDIT_VERDICTS = {"clean", "attention", "risk"}
UPSTREAM_KINDS = {"reference-only"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Valid values enum-fields frontmatter + version format (semver).
RISK_VALUES = {"read", "draft", "write", "external"}
ADAPTER_VALUES = {"claude", "cursor", "fable"}
LEVEL_VALUES = {"core", "foundation", "extension"}  # opt. field level (hierarchy)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
# Intra-skill relative links (snippets/…, references/…) in the body SKILL.md —
# should resolve. ../ and .agents/.claude (consumer project layout) and
# prose URL'we DO NOT check (false positives on upstream/imported).
INTRA_LINK_RE = re.compile(r"\]\((snippets/[^)#]+|references/[^)#]+)\)")
# lean SKILL.md: body - entry point, details in references/snippets (progressive disclosure).
# Soft threshold: body above it → warn (not error), hint to take out details.
# See docs/guide/skill-taxonomy.md.
LEAN_MAX_BODY_LINES = 150
# Cyrillic in downloadable EN-only canon SKILL.md. Hard gate on frontmatter
# `description` (resident ⊕ tier-0 — constant tax in EVERY request).
CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
# CUMULATIVE listing record gate thresholds (resident tier-0, P3.2 ratchet,
# re-based on merged field P3.5): first-party listing entry cap -
# 1 536 char (`name` + `description` + `when_to_use`, see budget.py `_listing_entry_tokens`/
# `_listing_entry_chars` — same formula `(description + " " + when_to_use).strip()`).
# DESC_WARN_MAX/DESC_ERROR_MAX — conservative INTERNAL reserve under this cap (not the cap itself):
# DESC_ERROR_MAX — hard ceiling, no exceptions (burn-down does not save above it).
# DESC_WARN_MAX — target rate; skills between WARN and ERROR are only legal if included in
# burn-down (inherited debt), otherwise - error (new debt prohibited). See
# scripts/desc-burndown.txt. Calculated BY TOTAL `description` + `when_to_use` — transfer
# trigger phrases between fields do not change this amount (§4 findings/P3-native-fields-context-cost).
DESC_WARN_MAX = 300
DESC_ERROR_MAX = 450
# Lower bound on the quality of an CUMULATIVE listing record as a TRIGGER (P3.5, ratchet according to the pattern
# top - see. desc-trigger-burndown.txt): entry must respond «when to call», not only
# «what is this» — phrase is searched in `description` + `when_to_use` together (same amount as gate
# lengths above), and not in one `description`, otherwise transfer the phrase to `when_to_use` when transferring
# would create a false new debt. Regular marker - a set of permanent markers, conditions of use (not
# skill genre).
DESC_TRIGGER_RE = re.compile(
    r"(use when|activate|use for|use to|when you|whenever|trigger|use this)", re.I
)

def _load_burndown_file(repo_root_pkg, filename):
    """scripts/<filename> → set('bucket/name'), comments(#)/ignore empty lines.
    General loader for desc-burndown.txt and desc-trigger-burndown.txt (same format)."""
    p = repo_root_pkg / "scripts" / filename
    if not p.is_file():
        return set()
    out = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        out.add(ln)
    return out

DESC_BURNDOWN = _load_burndown_file(root, "desc-burndown.txt")
DESC_BURNDOWN_SEEN = set()
DESC_BY_KEY = {}  # 'bucket/name' -> len(description + " " + when_to_use), rotten entry below
TRIG_BURNDOWN = _load_burndown_file(root, "desc-trigger-burndown.txt")
TRIG_BURNDOWN_SEEN = set()
TRIG_HAS_TRIGGER_BY_KEY = {}  # 'bucket/name' -> bool(trigger in description+when_to_use), rotten entry below


def _collect_block_scalar(lines, start):
    """Indent lines YAML-block scalar starting from lines[start] → (lines, next_i).
    Empty ones are stored as hyphens; tails are trimmed (clip-chomp). Mirrors
    aicore.util.text._collect_block_scalar (gate should read as generate)."""
    block, i = [], start
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "---":
            break
        if ln.strip() == "":
            block.append("")
        elif ln.startswith((" ", "\t")):
            block.append(ln.strip())
        else:
            break
        i += 1
    while block and block[-1] == "":
        block.pop()
    return block, i


def parse_frontmatter(path):
    """Frontmatter of the first ---block, or None if there is no block/is not closed.

    Collects YAML-block scalars (`key: |` / `key: >` + opt. Chomp) and cuts BOM
    (utf-8-sig) — ELSE `description: >` gives gate marker only '>', and Cyrillic/
    real length (block) descriptions are not checked = false green. Reads the same way
    like generate-path aicore.content.skill.read_frontmatter (conscious
    self-contained take: the heredoc does not import the package)."""
    lines = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm, i, terminated = {}, 1, False
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            terminated = True
            break
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if value[:1] in ("|", ">") and all(c in "+-0123456789" for c in value[1:]):
                block, i = _collect_block_scalar(lines, i + 1)
                fm[key] = (" " if value[0] == ">" else "\n").join(block)
                continue
            fm[key] = value.strip('"').strip("'")
        i += 1
    return fm if terminated else None  # unterminated block → None


def parse_inline_list(value):
    """Inline YAML list ('[a, "b", c]') -> list of strings; anything else -> []."""
    value = (value or "").strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
    return [i for i in items if i]


def load_upstream(skill_dir):
    f = skill_dir / "upstream.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{f.relative_to(root)}: invalid JSON: {e}")
        return {}


# --- 1. SKILL.md frontmatter ---------------------------------------------
skill_files = sorted(root.glob("skills/**/SKILL.md"))
meta_skill = root / "generate-skill/generate-skill/SKILL.md"
if meta_skill.exists():
    skill_files.append(meta_skill)

for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    skill_dir = skill_md.parent
    upstream = load_upstream(skill_dir)
    fm = parse_frontmatter(skill_md)

    if fm is None:
        if upstream is not None and upstream.get("strategy") == "replace":
            errors.append(
                f"{rel}: no frontmatter and upstream strategy=replace — "
                f"frontmatter-less upstreams must use strategy=notify"
            )
        else:
            errors.append(f"{rel}: missing frontmatter block")
        continue

    required = ["name", "description"] if upstream is not None \
        else ["name", "bucket", "version", "description"]
    for field in required:
        if not fm.get(field):
            errors.append(f"{rel}: missing required frontmatter field: {field}")

    # --- 1·tokens: description — EN-canon (resident ⊕ tier-0), without Cyrillic, not bloated ---
    desc = fm.get("description", "")
    if CYRILLIC_RE.search(desc):
        errors.append(f"{rel}: frontmatter description contains Cyrillic - SKILL.md this "
                      f"EN-only canon (resident tier-0 in EVERY request)")
    if CYRILLIC_RE.search(fm.get("name", "")):
        errors.append(f"{rel}: frontmatter name contains Cyrillic (skill name - EN-kebab)")
    # CUMULATIVE listing record - same formula as budget.py
    # `_listing_entry_tokens`/`_listing_entry_chars`: `description` + `when_to_use` one
    # line (empty when_to_use does not change the result). Length gates/trigger below read
    # EXACTLY her, not naked `desc`, — otherwise transfer the phrase to `when_to_use` breaks both gates.
    listing_text = (desc + " " + fm.get("when_to_use", "")).strip()
    # bucket key - from PATH (not frontmatter): upstream-skills often without a field `bucket`.
    _desc_parts = rel.parts
    _desc_bn = _desc_parts[1] if _desc_parts[0] == "skills" and len(_desc_parts) > 2 else None
    _desc_nm = fm.get("name", "").strip('"').strip("'") or skill_dir.name
    _desc_key = f"{_desc_bn}/{_desc_nm}" if _desc_bn and _desc_nm else None
    if _desc_key:
        DESC_BY_KEY[_desc_key] = len(listing_text)
    if len(listing_text) > DESC_ERROR_MAX:
        errors.append(f"{rel}: listing entry (description+when_to_use) {len(listing_text)} char "
                      f"(> {DESC_ERROR_MAX} hard-ceiling) — shorten (triggers can be shrunk), "
                      f"burn-down does not help above {DESC_ERROR_MAX}, see skiller budget")
    elif len(listing_text) > DESC_WARN_MAX:
        if _desc_key and _desc_key in DESC_BURNDOWN:
            DESC_BURNDOWN_SEEN.add(_desc_key)
            warnings.append(f"{rel}: listing entry (description+when_to_use) "
                            f"{len(listing_text)} char (> {DESC_WARN_MAX}) — inherited debt "
                            f"in scripts/desc-burndown.txt (legal, but cut back next time "
                            f"edit)")
        else:
            errors.append(f"{rel}: listing entry (description+when_to_use) "
                          f"{len(listing_text)} char (> {DESC_WARN_MAX}) and NOT in "
                          f"scripts/desc-burndown.txt — new debt prohibited (ratchet P3.2): "
                          f"shorten the entry to <= {DESC_WARN_MAX} character or add to "
                          f"desc-burndown.txt with justification")

    # --- 1·trigger: listing entry responds «when to call» (P3.5 ratchet, upstream skip) ---
    if _desc_key and upstream is None:
        has_trigger = bool(DESC_TRIGGER_RE.search(listing_text))
        TRIG_HAS_TRIGGER_BY_KEY[_desc_key] = has_trigger
        if not has_trigger:
            if _desc_key in TRIG_BURNDOWN:
                TRIG_BURNDOWN_SEEN.add(_desc_key)
                warnings.append(f"{rel}: description+when_to_use without trigger phrase (use "
                                f"when/activate/use for/…) — inherited debt in "
                                f"scripts/desc-trigger-burndown.txt (legal, but fix it when "
                                f"next edit)")
            else:
                errors.append(f"{rel}: description+when_to_use without trigger phrase (use "
                              f"when/activate/use for/use to/when you/whenever/trigger/use "
                              f"this) and NOT in scripts/desc-trigger-burndown.txt — new debt "
                              f"prohibited (ratchet P3.5): describe WHEN to call the skill (in description "
                              f"or when_to_use), or add to desc-trigger-burndown.txt with "
                              f"justification")

    # --- 1a. enum / semver / bucket-vs-dir / declared snippets / intra-links ---
    parts = rel.parts
    path_bucket = parts[1] if parts[0] == "skills" and len(parts) > 2 else None

    risk = fm.get("risk", "")
    if risk and risk not in RISK_VALUES:
        errors.append(f"{rel}: risk '{risk}' not from {sorted(RISK_VALUES)}")

    level = fm.get("level", "")
    if level and level not in LEVEL_VALUES:
        errors.append(f"{rel}: level '{level}' not from {sorted(LEVEL_VALUES)}")

    bad_adapters = [a for a in parse_inline_list(fm.get("adapters", ""))
                    if a not in ADAPTER_VALUES]
    if bad_adapters:
        errors.append(f"{rel}: unknown adapters {bad_adapters} "
                      f"(valid {sorted(ADAPTER_VALUES)})")

    # version/bucket — only for local (upstream-skills are kept to a minimum frontmatter)
    if upstream is None:
        ver = fm.get("version", "")
        if ver and not SEMVER_RE.match(ver):
            errors.append(f"{rel}: version '{ver}' not semver (\\d+.\\d+.\\d+)")
        fm_bucket = fm.get("bucket", "")
        if path_bucket and fm_bucket and fm_bucket != path_bucket:
            errors.append(f"{rel}: frontmatter bucket '{fm_bucket}' != directory "
                          f"'{path_bucket}'")

    # declared in frontmatter snippets must exist on disk
    for snip in parse_inline_list(fm.get("snippets", "")):
        if not (skill_dir / "snippets" / snip).exists():
            errors.append(f"{rel}: snippets[{snip}] is declared, but the file is not on disk")

    # intra-skill links snippets/… references/… in the body - must resolve
    body = skill_md.read_text(encoding="utf-8")
    for m in INTRA_LINK_RE.finditer(body):
        tgt = m.group(1).split("#")[0]
        if not (skill_dir / tgt).exists():
            errors.append(f"{rel}: broken link to {tgt} (no file)")

    # lean SKILL.md: body (without frontmatter) above threshold → soft warn.
    # upstream-skills (imported/external) skip - their volume is intentional (adapted
    # copy of external document), lean-standard applies to COPYRIGHT local-skills.
    lines = body.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
    body_lines = len([ln for ln in lines[body_start:] if ln.strip()])
    if body_lines > LEAN_MAX_BODY_LINES and load_upstream(skill_dir) is None:
        warnings.append(f"{rel}: body SKILL.md {body_lines} non-empty lines "
                        f"(> {LEAN_MAX_BODY_LINES}) — put the details in references/snippets "
                        f"(lean SKILL.md, docs/guide/skill-taxonomy.md)")

# --- 1b. desc-burndown.txt — rotten records (one-way ratchet, P3.2/P3.5) -----------
# The entry is legal, only for now: the skill exists AND its listing entry
# (description+when_to_use) still > DESC_WARN_MAX. Otherwise - rotten (skill
# deleted/renamed, or already shortened to normal) — remove the line.
for _bn_key in sorted(DESC_BURNDOWN):
    if _bn_key not in DESC_BY_KEY:
        warnings.append(f"scripts/desc-burndown.txt: '{_bn_key}' — rotten recording (no skill "
                        f"in the registry below this bucket/name), remove the line")
    elif DESC_BY_KEY[_bn_key] <= DESC_WARN_MAX:
        warnings.append(f"scripts/desc-burndown.txt: '{_bn_key}' — rotten recording (entry "
                        f"listing already {DESC_BY_KEY[_bn_key]} char <= {DESC_WARN_MAX}), remove "
                        f"line")

# --- 1b·trigger. desc-trigger-burndown.txt — rotten records (one-way ratchet, P3.5) -----
# The entry is legal, only for now: the skill exists AND its listing entry
# (description+when_to_use) still without a trigger.
for _tb_key in sorted(TRIG_BURNDOWN):
    if _tb_key not in TRIG_HAS_TRIGGER_BY_KEY:
        warnings.append(f"scripts/desc-trigger-burndown.txt: '{_tb_key}' — rotten recording "
                        f"(skill is not in the registry under this bucket/name), remove the line")
    elif TRIG_HAS_TRIGGER_BY_KEY[_tb_key]:
        warnings.append(f"scripts/desc-trigger-burndown.txt: '{_tb_key}' — rotten recording "
                        f"(description+when_to_use already carries a trigger phrase), remove the line")

# --- 1c. CORE-nine - mandatory body sections (P8.8, ratchet) ------------
# A complete gate for all skills is impossible (measurement: activation section is carried
# 38/160). Narrowed to resident CORE_SKILLS (core-policy.json::skills, 9 pcs.).
# (b) links section - ERROR no exceptions (debt zero, 9/9 pass).
# (a) activation section - ERROR with Ratchet skill-sections-burndown.txt (that
# the same mechanics as desc-burndown.txt above): entry is legal as long as skill
# exists And it still doesn't have a section.
CORE_ACTIVATION_RE = re.compile(r"(?i)^\s*\d*\.?\s*(when\b|activate\b)")
CORE_LINKS_RE = re.compile(r"(?i)^\s*\d*\.?\s*(links|references|related skills|related)\s*$")
HEADING2_RE = re.compile(r"^##[^#](.*)$", re.MULTILINE)

def _load_sections_burndown(repo_root_pkg):
    """scripts/skill-sections-burndown.txt → set('bucket/name'); same format,
    what desc-burndown.txt."""
    p = repo_root_pkg / "scripts" / "skill-sections-burndown.txt"
    if not p.is_file():
        return set()
    out = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        out.add(ln)
    return out

SECTIONS_BURNDOWN = _load_sections_burndown(root)
SECTIONS_BURNDOWN_SEEN = set()

_core_policy_skills = []
if _core_policy_path.is_file():
    try:
        _csp = json.loads(_core_policy_path.read_text(encoding="utf-8"))
        if isinstance(_csp, dict):
            _core_policy_skills = _csp.get("skills", []) or []
    except json.JSONDecodeError:
        pass  # already ERROR from core-policy.json-checks above

for _core_key in _core_policy_skills:
    _core_skill_md = root / "skills" / _core_key / "SKILL.md"
    if not _core_skill_md.is_file():
        continue  # already ERROR from core-policy.json-checks above
    _core_headings = [m.group(1).strip()
                      for m in HEADING2_RE.finditer(_core_skill_md.read_text(encoding="utf-8"))]
    has_activation = any(CORE_ACTIVATION_RE.match(h) for h in _core_headings)
    has_links = any(CORE_LINKS_RE.match(h) for h in _core_headings)
    if not has_links:
        errors.append(f"skills/{_core_key}/SKILL.md: no links section "
                      f"(##Links/References/Related skills/Related) — CORE-skill")
    if not has_activation:
        if _core_key in SECTIONS_BURNDOWN:
            SECTIONS_BURNDOWN_SEEN.add(_core_key)
            warnings.append(f"skills/{_core_key}/SKILL.md: no activation section and skill "
                            f"in scripts/skill-sections-burndown.txt (inherited debt)")
        else:
            errors.append(f"skills/{_core_key}/SKILL.md: no activation section and skill "
                          f"not in skill-sections-burndown.txt")

for _sb_key in sorted(SECTIONS_BURNDOWN):
    if _sb_key not in _core_policy_skills:
        warnings.append(f"scripts/skill-sections-burndown.txt: '{_sb_key}' — rotten "
                        f"entry (skill is not in CORE-nine core-policy.json), remove the line")
    elif _sb_key not in SECTIONS_BURNDOWN_SEEN:
        warnings.append(f"scripts/skill-sections-burndown.txt: '{_sb_key}' — rotten "
                        f"entry (skill already has an activation section), remove the line")

# --- 2. upstream.json -----------------------------------------------------
for up_file in sorted(root.glob("skills/**/upstream.json")) + \
        sorted((root / "generate-skill").glob("**/upstream.json")):
    rel = up_file.relative_to(root)
    skill_dir = up_file.parent
    if not (skill_dir / "SKILL.md").exists():
        errors.append(f"{rel}: upstream.json without sibling SKILL.md")
    try:
        data = json.loads(up_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue

    if data.get("schema_version") != 1:
        errors.append(f"{rel}: schema_version must be 1")
    if data.get("source") not in UPSTREAM_SOURCES:
        errors.append(f"{rel}: source must be one of {sorted(UPSTREAM_SOURCES)}")
    if data.get("strategy") not in UPSTREAM_STRATEGIES:
        errors.append(f"{rel}: strategy must be one of {sorted(UPSTREAM_STRATEGIES)}")
    # fork: fork skill with local edits. review_pending=true — upstream parted ways with
    # mirror, needs manual modification → GATE: blocking validation (and thereby registry/release),
    # until the agent transfers the diff and does update-upstreams.sh --resolve.
    if data.get("strategy") == "fork":
        rp = data.get("review_pending")
        if rp is not None and not isinstance(rp, bool):
            errors.append(f"{rel}: review_pending must be a boolean")
        if rp is True:
            errors.append(
                f"{rel}: review_pending=true — upstream fork separated from the mirror; "
                f"check diff and transfer the changes to SKILL.md, then "
                f"scripts/update-upstreams.sh --resolve --skill <id>")
        lr = data.get("last_review", "")
        if lr and not DATE_RE.match(lr):
            errors.append(f"{rel}: last_review must be YYYY-MM-DD or empty")
    # merge: composite of ≥2 external sources. origins[] fixes provenance with
    # roles (base — is taken as a basis; supplement/«suggest» — what's extra
    # merged). Manual sync: on the drift of any origin merge.review_pending=true
    # blocks validation (and registry/release), until the agent re-merges and
    # will remove the gate (scripts/update-upstreams.sh --resolve).
    if data.get("strategy") == "merge":
        origins = data.get("origins")
        if not isinstance(origins, list) or len(origins) < 2:
            errors.append(f"{rel}: strategy=merge requires origins[] from ≥2 sources "
                          f"(base + ≥1 supplement)")
            origins = []
        roles = []
        for k, org in enumerate(origins):
            if not isinstance(org, dict):
                errors.append(f"{rel}: origins[{k}] must be an object")
                continue
            for key in ("repo", "role", "url", "sha256", "fetched_at"):
                if not org.get(key):
                    errors.append(f"{rel}: origins[{k}] missing key: {key}")
            role = org.get("role", "")
            if role and role not in ORIGIN_ROLES:
                errors.append(f"{rel}: origins[{k}].role '{role}' not from "
                              f"{sorted(ORIGIN_ROLES)}")
            roles.append(role)
            of = org.get("fetched_at", "")
            if of and not DATE_RE.match(of):
                errors.append(f"{rel}: origins[{k}].fetched_at must be YYYY-MM-DD")
        if origins and roles.count("base") != 1:
            errors.append(f"{rel}: strategy=merge requires EXACTLY one origin role=base")
        if origins and "supplement" not in roles:
            errors.append(f"{rel}: strategy=merge requires ≥1 origin role=supplement")
        merge = data.get("merge") or {}
        if not isinstance(merge, dict):
            errors.append(f"{rel}: merge must be an object")
            merge = {}
        rp = merge.get("review_pending")
        if rp is not None and not isinstance(rp, bool):
            errors.append(f"{rel}: merge.review_pending must be a boolean")
        if rp is True:
            errors.append(
                f"{rel}: merge.review_pending=true — one of origins separated from "
                f"mirror; re-merge sources in SKILL.md, then "
                f"scripts/update-upstreams.sh --resolve --skill <id>")
        mlr = merge.get("last_review", "")
        if mlr and not DATE_RE.match(mlr):
            errors.append(f"{rel}: merge.last_review must be YYYY-MM-DD or empty")
    elif data.get("origins") is not None:
        errors.append(f"{rel}: origins[] is only valid when strategy=merge")
    if data.get("source") == "file":
        warnings.append(f"{rel}: source=file is for local fixtures/tests only")

    files = data.get("files")
    if not isinstance(files, list) or not files:
        errors.append(f"{rel}: files must be a non-empty array")
        continue
    for i, entry in enumerate(files):
        for key in ("path", "url", "sha256", "fetched_at"):
            if key not in entry:
                errors.append(f"{rel}: files[{i}] missing key: {key}")
        path = entry.get("path", "")
        if path:
            target = (skill_dir / path).resolve()
            if not str(target).startswith(str(skill_dir.resolve())):
                errors.append(f"{rel}: files[{i}].path escapes skill dir: {path}")
            elif not target.exists():
                errors.append(f"{rel}: files[{i}].path does not exist: {path}")
        fetched = entry.get("fetched_at", "")
        if fetched and not DATE_RE.match(fetched):
            errors.append(f"{rel}: files[{i}].fetched_at must be YYYY-MM-DD or empty")

    # body_path (P7.3, thin-navigator): optional - path (regarding skill_dir),
    # where the upstream body actually lies when SKILL.md became locally written
    # a navigator, NOT an upstream mirror (see update-upstreams.sh, docs/guide/
    # upstream-sync.md). Additive field; absence = body in SKILL.md (back-compat).
    # It MUST match one of files[].path — otherwise update-upstreams.sh not
    # will count sha/drift along the declared body (silent tracking hole).
    body_path = data.get("body_path")
    if body_path is not None:
        if not isinstance(body_path, str) or not body_path:
            errors.append(f"{rel}: body_path must be a non-empty string")
        else:
            bp_target = (skill_dir / body_path).resolve()
            if not str(bp_target).startswith(str(skill_dir.resolve())):
                errors.append(f"{rel}: body_path escapes skill dir: {body_path}")
            elif not bp_target.exists():
                errors.append(f"{rel}: body_path does not exist: {body_path}")
            tracked_paths = {f.get("path") for f in files if isinstance(f, dict)}
            if body_path not in tracked_paths:
                errors.append(
                    f"{rel}: body_path '{body_path}' is not tracked in files[] — "
                    f"update-upstreams.sh would not check its sha/drift")
            # strategy=replace autowrites files[].path on --apply (unlike fork/merge,
            # which only stage an incoming copy for manual review) — a stray SKILL.md
            # entry there would silently clobber the hand-authored navigator.
            if data.get("strategy") == "replace" and "SKILL.md" in tracked_paths \
                    and body_path != "SKILL.md":
                errors.append(
                    f"{rel}: body_path set (thin-navigator) but files[] also tracks "
                    f"SKILL.md under strategy=replace — update-upstreams.sh --apply "
                    f"would overwrite the hand-authored navigator; drop the SKILL.md "
                    f"files[] entry")

    # --- audit: human verdict on the bundle (P5.11, thread (B) OQ-6) --------
    # THE ABSENCE of a block is NOT caught by this gate, but by the triage stage update-upstreams.sh
    # --check (find AUDIT_MISSING): «there is no bundle without a verdict» — rule
    # distributions, not a structural failure of the file. Here the FORM of the record is checked:
    # silent attention indistinguishable from a typo, verdict without the address of the reader
    # is meaningless, and a verdict without its own anchor cannot go rotten.
    entry_paths = [entry.get("path", "") for entry in files if isinstance(entry, dict)]
    ref_only = bool(entry_paths) and not any(entry_paths)
    kind = data.get("kind")
    if kind is not None and kind not in UPSTREAM_KINDS:
        errors.append(f"{rel}: kind must be one of {sorted(UPSTREAM_KINDS)}")
    elif kind == "reference-only" and not ref_only:
        errors.append(f"{rel}: kind=reference-only, but files[] carries local "
                      f"mirrors (non-empty path) — machine sign, not an opinion")
    elif kind is None and ref_only:
        errors.append(f"{rel}: all files[].path are empty (bundle does not vendor anything) — "
                      f"announce kind: \"reference-only\", otherwise class machine "
                      f"indistinguishable from vendor")

    audit = data.get("audit")
    if audit is not None and not isinstance(audit, dict):
        errors.append(f"{rel}: audit must be an object")
    elif isinstance(audit, dict):
        verdict = audit.get("verdict")
        if verdict not in AUDIT_VERDICTS:
            errors.append(f"{rel}: audit.verdict must be one of "
                          f"{sorted(AUDIT_VERDICTS)}")
        at = audit.get("at", "")
        if not at or not DATE_RE.match(at):
            errors.append(f"{rel}: audit.at must be YYYY-MM-DD (date the bundle was read)")
        if not audit.get("by"):
            errors.append(f"{rel}: audit.by missing — address of the bundle reader "
                          f"(<PLAN-ID> <item> or manual reading date); entry "
                          f"without an address means nothing")
        if verdict in ("attention", "risk") and not audit.get("note"):
            errors.append(f"{rel}: audit.note is required when verdict={verdict} — "
                          f"silent verdict indistinguishable from a typo")
        if ref_only:
            if "upstream_sha" in audit:
                errors.append(f"{rel}: audit.upstream_sha when kind=reference-only "
                              f"must be omitted - there is nothing to anchor, there are no mirrors")
        elif not SHA256_RE.match(audit.get("upstream_sha", "")):
            errors.append(f"{rel}: audit.upstream_sha must be a sha256 hex digest — "
                          f"without its own anchor, the verdict cannot go rotten "
                          f"(update-upstreams.sh: AUDIT_STALE)")

# --- 3. profiles/*.json ---------------------------------------------------
# Taxonomy Canon - aicore.util.project.PROJECT_TYPES; here is a self-contained take
# (the heredoc does not import the package on purpose; hold in sync with
#  aicore/util/project.py). Links to presets/packs/mcp live in the package
# configured environment publisher — checked only when available in this host.
PROJECT_TYPE_IDS = {
    "obsidian-vault", "laravel-project", "php-package", "dart-flutter",
    "python-backend", "node-frontend", "node-package", "standalone",
}
AA_MODES = {"strict", "permissive", "bypass", "off"}
MEM_MODES = {"file", "federation", "agentmemory", "off"}
MODEL_TIERS = {"inherit", "opus", "sonnet", "haiku"}
# Host-selected publisher; no repository partner names or fixed package layout.
hc_dir = None
_host = None
if (root / "lib" / "skiller" / "host.py").is_file():
    sys.path[:0] = [str(root / "lib"), str(repo_root)]
    core_root = root.parent.parent
    if (core_root / "core").is_dir():
        sys.path.insert(0, str(core_root))
    from skiller.host import load_host, host_plugin_dirs
    _host = load_host(root)
    MEM_MODES.update(_host.mcp_servers)
    _environment = _host.commands.get("environment")
    if _environment is not None and "/" in _environment.argv[0]:
        hc_dir = (_host.root / _environment.argv[0]).parent.parent / "configs" / "claude-code"
profile_names = set()
profiles_dir = root / "profiles"
if profiles_dir.is_dir():
    for prof in sorted(profiles_dir.glob("*.json")):
        rel = prof.relative_to(root)
        try:
            data = json.loads(prof.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        profile_names.add(prof.stem)
        if data.get("name") != prof.stem:
            errors.append(f"{rel}: name must match filename ({prof.stem})")
        buckets = data.get("buckets")
        if not isinstance(buckets, list) or not buckets:
            errors.append(f"{rel}: buckets must be a non-empty array")
        elif buckets != ["*"]:
            for b in buckets:
                if not (root / "skills" / b).is_dir():
                    errors.append(f"{rel}: unknown bucket: {b}")
        # --- extended options keys: agent_pack/presets/mcp/hooks/model_tiers ---
        pack = data.get("agent_pack")
        if pack is not None and not isinstance(pack, (str, list)):
            errors.append(f"{rel}: agent_pack must be a string or list")
        packs = [pack] if isinstance(pack, str) else (pack if isinstance(pack, list) else [])
        if hc_dir is not None and hc_dir.is_dir():
            for pk in packs:
                if not (hc_dir / "agent-packs" / str(pk) / "pack.json").exists():
                    errors.append(f"{rel}: agent_pack '{pk}' — no pack.json in environment publisher")
            for preset in data.get("harness_presets", []) or []:
                if not (hc_dir / f"settings.{preset}.json").exists():
                    errors.append(f"{rel}: harness_preset '{preset}' — no settings.{preset}.json")
            for srv in data.get("mcp", []) or []:
                if not (hc_dir / "mcp" / f"{srv}.json").exists():
                    errors.append(f"{rel}: mcp '{srv}' — no mcp/{srv}.json")
        hooks = data.get("hooks") or {}
        if not isinstance(hooks, dict):
            errors.append(f"{rel}: hooks must be an object")
        else:
            aa = hooks.get("auto_approve")
            if aa is not None and aa not in AA_MODES:
                errors.append(f"{rel}: hooks.auto_approve '{aa}' not from {sorted(AA_MODES)}")
            mem = hooks.get("memory")
            if mem is not None and mem not in MEM_MODES:
                errors.append(f"{rel}: hooks.memory '{mem}' not from {sorted(MEM_MODES)}")
        tiers = data.get("model_tiers") or {}
        if not isinstance(tiers, dict):
            errors.append(f"{rel}: model_tiers must be an object")
        else:
            for role, tier in tiers.items():
                if tier not in MODEL_TIERS:
                    errors.append(f"{rel}: model_tiers.{role} '{tier}' "
                                  f"not from {sorted(MODEL_TIERS)}")
    # --- 3b. coverage: each id taxonomy has profiles/<id>.json ---
    missing = PROJECT_TYPE_IDS - profile_names
    if missing:
        errors.append(f"profiles/: no profiles for types {sorted(missing)} "
                      f"(see core.project.PROJECT_TYPES)")

# --- 4. skills.json -------------------------------------------------------
reg = root / "skills.json"
if reg.exists():
    try:
        json.loads(reg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"skills.json: invalid JSON: {e}")
else:
    errors.append("skills.json not found")

# --- 5. snippet manifests -------------------------------------------------
for manifest in sorted(root.glob("skills/**/snippets/index.json")):
    rel = manifest.relative_to(root)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    for s in data.get("snippets", []):
        f = manifest.parent / s.get("file", "")
        if not f.exists():
            errors.append(f"{rel}: missing snippet: {s.get('file')}")

# --- 5b. evals/ (behavioral skill tests) -------------------------------
# Structural check of existing evals.json/pressure.json/triggers.json (if
# started) + coverage summary. Deep semantics (types of assertions, run) — in
# lib/skiller/eval.py + tests/test_eval.py; here is only a soft format gate.
# Coverage - ONE line (not per-skill warning), to avoid making the output noisy.
def _check_cases(node, where, key):
    cases = node.get(key)
    if not isinstance(cases, list) or not cases:
        errors.append(f"{where}: '{key}' must be a non-empty array")
        return
    ids = set()
    for k, c in enumerate(cases):
        w = f"{where}.{key}[{k}]"
        if not isinstance(c, dict):
            errors.append(f"{w}: case must be an object"); continue
        cid = c.get("id")
        if cid is None:
            errors.append(f"{w}: no id")
        elif cid in ids:
            errors.append(f"{w}: duplicate id {cid!r}")
        else:
            ids.add(cid)
        if not c.get("prompt"):
            errors.append(f"{w}: no non-empty prompt")
        for j, a in enumerate(c.get("assertions", []) or []):
            if not isinstance(a, dict) or not a.get("type") or "value" not in a:
                errors.append(f"{w}.assertions[{j}]: need an object with type+value")

local_total = local_with_evals = 0
for skill_md in sorted(root.glob("skills/*/*/SKILL.md")):
    sd = skill_md.parent
    if (sd / "upstream.json").exists():
        continue                       # eval-standard - for copyright (not upstream)
    local_total += 1
    ev = sd / "evals" / "evals.json"
    if ev.exists():
        local_with_evals += 1
for ev_file in sorted(root.glob("skills/*/*/evals/evals.json")):
    rel = ev_file.relative_to(root)
    try:
        data = json.loads(ev_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}"); continue
    if not isinstance(data, dict) or not data.get("skill"):
        errors.append(f"{rel}: need an object with a field skill")
    else:
        _check_cases(data, str(rel), "cases")
for pr_file in sorted(root.glob("skills/*/*/evals/pressure.json")):
    rel = pr_file.relative_to(root)
    try:
        data = json.loads(pr_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}"); continue
    if not isinstance(data, dict) or not data.get("skill"):
        errors.append(f"{rel}: need an object with a field skill")
    else:
        _check_cases(data, str(rel), "scenarios")
for tr_file in sorted(root.glob("skills/*/*/evals/triggers.json")):
    rel = tr_file.relative_to(root)
    try:
        data = json.loads(tr_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}"); continue
    for key in ("should_trigger", "should_not"):
        v = data.get(key) if isinstance(data, dict) else None
        if not isinstance(v, list) or not v:
            errors.append(f"{rel}: '{key}' must be a non-empty array")

# --- 5c. Pressure-cases are required when evals.json + coating triggers[] --
# Zero debt (measurement: 4/4 evals.json are already carrying pressure.json) ⇒ ERROR without Ratchet.
# triggers[]-coating - WARNING (field is new, existing scripts do not have it yet).
for skill_md in sorted(root.glob("skills/*/*/SKILL.md")):
    sd = skill_md.parent
    if (sd / "upstream.json").exists():
        continue
    ev_p8 = sd / "evals" / "evals.json"
    if not ev_p8.exists():
        continue
    rel_sd = sd.relative_to(root)
    pr_p8 = sd / "evals" / "pressure.json"
    if not pr_p8.exists():
        errors.append(f"{rel_sd}: yes evals.json, no pressure.json")
        continue
    try:
        pr_p8_data = json.loads(pr_p8.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        continue  # already ERROR from 5b above
    p8_scenarios = pr_p8_data.get("scenarios") if isinstance(pr_p8_data, dict) else None
    if not isinstance(p8_scenarios, list) or not p8_scenarios:
        errors.append(f"{rel_sd}: yes evals.json, pressure.json without scripts")
        continue
    tr_p8 = sd / "evals" / "triggers.json"
    if not tr_p8.exists():
        continue
    try:
        tr_p8_data = json.loads(tr_p8.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        continue  # already ERROR from 5b above
    should_trigger = tr_p8_data.get("should_trigger") if isinstance(tr_p8_data, dict) else None
    if not isinstance(should_trigger, list):
        continue
    covered = set()
    for _sc in p8_scenarios:
        if isinstance(_sc, dict):
            covered.update(t for t in (_sc.get("triggers") or []) if isinstance(t, str))
    for q in should_trigger:
        if q not in covered:
            warnings.append(f"{rel_sd}: should_trigger {q!r} is not covered by any "
                            f"pressure-script (field triggers[])")

# Host bootstrap projections, hashes and completeness are owned by registry --check.

# --- 6. buckets.json --------------------------------------------------------
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
bucket_dirs = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())
bucket_meta = {}
meta_file = root / "buckets.json"
if not meta_file.exists():
    errors.append("buckets.json not found")
else:
    try:
        bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"buckets.json: invalid JSON: {e}")
        bucket_meta = {}
    for b in bucket_dirs:
        if b not in bucket_meta:
            errors.append(f"buckets.json: missing entry for bucket: {b}")
    for b, meta in bucket_meta.items():
        # Alias-bucket (P7.5, merging buckets - mechanism without application, D14): metadata-
        # entry WITHOUT skills/<bucket>, `alias_of` points to the target bucket. Not orphan.
        is_alias = isinstance(meta, dict) and meta.get("alias_of")
        if b not in bucket_dirs and not is_alias:
            errors.append(f"buckets.json: entry without skills/ dir: {b}")
        if is_alias and meta["alias_of"] not in bucket_dirs:
            errors.append(f"buckets.json: {b}: alias_of points to a non-existent "
                          f"bucket: {meta['alias_of']}")
        if not (isinstance(meta, dict) and meta.get("description")):
            errors.append(f"buckets.json: {b}: description must be non-empty")


# --- 6b. presets/*.json (named skill clusters) ----------------------
# Preset = group of skills for vendor-samples: {name, description, extends?,
# buckets?, include?}. resolve_skillset reveals presets → buckets/include.
# Checking: name==file (kebab), non-empty description, extends/buckets/include
# resolve, cycles in extends no. Catalog optional (graceful skip).
presets_dir = root / "presets"
if presets_dir.is_dir():
    skill_names, skill_paths = set(), set()
    for skill_md in skill_files:
        fm = parse_frontmatter(skill_md) or {}
        nm = (fm.get("name", "") or "").strip().strip('"').strip("'")
        if nm:
            skill_names.add(nm)
        parts = skill_md.parent.relative_to(root).parts
        if len(parts) >= 3 and parts[0] == "skills":
            skill_paths.add("/".join(parts[1:]))  # bucket/rel
    preset_names = {p.stem for p in presets_dir.glob("*.json")}
    preset_extends = {}
    for pf in sorted(presets_dir.glob("*.json")):
        rel = pf.relative_to(root)
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        if data.get("name") != pf.stem:
            errors.append(f"{rel}: name must match filename ({pf.stem})")
        if not KEBAB_RE.match(pf.stem):
            errors.append(f"{rel}: preset name must be kebab-case")
        if not data.get("description"):
            errors.append(f"{rel}: description must be non-empty")
        ext = data.get("extends", []) or []
        if not isinstance(ext, list):
            errors.append(f"{rel}: extends must be a list")
            ext = []
        for parent in ext:
            if parent not in preset_names:
                errors.append(f"{rel}: extends unknown preset '{parent}'")
        preset_extends[pf.stem] = [e for e in ext if e in preset_names]
        for b in data.get("buckets", []) or []:
            if b not in bucket_dirs:
                errors.append(f"{rel}: unknown bucket '{b}'")
        for tok in data.get("include", []) or []:
            if tok not in skill_names and tok not in skill_paths:
                errors.append(f"{rel}: include '{tok}' does not resolve into skill "
                              f"(need name or bucket/rel)")
    # loops in extends (iterative DFS, white/grey/black)
    PW, PG, PB = 0, 1, 2
    pcol = {n: PW for n in preset_extends}
    for pstart in sorted(preset_extends):
        if pcol[pstart] != PW:
            continue
        pstack = [(pstart, iter(preset_extends.get(pstart, [])))]
        pcol[pstart] = PG
        ppath = [pstart]
        while pstack:
            pnode, pit = pstack[-1]
            padv = False
            for pdep in pit:
                if pcol.get(pdep) == PG:
                    cyc = ppath[ppath.index(pdep):] + [pdep]
                    errors.append(f"presets: extends cycle: {' -> '.join(cyc)}")
                elif pcol.get(pdep) == PW:
                    pcol[pdep] = PG
                    ppath.append(pdep)
                    pstack.append((pdep, iter(preset_extends.get(pdep, []))))
                    padv = True
                    break
            if not padv:
                pcol[pnode] = PB
                ppath.pop()
                pstack.pop()


# --- 7. plugin manifests (.claude-plugin/) ----------------------------------
def expected_skills_dirs(plugin_root):
    """Same algorithm as sync.sh: parents of skill dirs, ./-prefixed."""
    dirs = set()
    for skill_md in plugin_root.rglob("SKILL.md"):
        rel = skill_md.parent.parent.relative_to(plugin_root)
        dirs.add("./" if str(rel) == "." else f"./{rel.as_posix()}")
    return sorted(dirs)


STALE_HINT = "run 'skiller registry' (or ./sync.sh --update-registry)"
# P1.2: a private/source-only bucket (repository-bootstrap) never gets an ordinary
# `.claude-plugin/plugin.json` — `publication.py`'s catalog builder excludes it from unit
# construction outright, so validating one here would demand an artifact the generator never
# produces. Same `private_source_only` flag `skillset.py`/`publication.py` already read.
plugin_roots = {b: root / "skills" / b for b in bucket_dirs
               if not (isinstance(bucket_meta.get(b), dict)
                       and bucket_meta[b].get("private_source_only"))}
plugin_roots["generate-skill"] = root / "generate-skill"
# Management plugin (command person CLI, without skills) — is validated as a regular plugin,
# if the directory exists; registry.py adds it to marketplace.json synchronously.
if (root / "skm" / ".claude-plugin" / "plugin.json").exists():
    plugin_roots["skm"] = root / "skm"

# Neighboring monorepo packages (packages/<name>, except swissknifeman) — command/MCP-plugins
# without skills-fields; them plugin.json — source of truth, registry adds them to marketplace.
# Here we only collect their names for match-checks (full validation - in their package).
sibling_plugin_names = []
if _host is not None:
    for pkg in host_plugin_dirs(repo_root, root, _host):
        pj = pkg / ".claude-plugin" / "plugin.json"
        try:
            sibling_plugin_names.append(
                json.loads(pj.read_text(encoding="utf-8")).get("name", pkg.name))
        except json.JSONDecodeError as e:
            errors.append(f"{pj.relative_to(repo_root)}: invalid JSON: {e}")

for plugin_name, plugin_root in sorted(plugin_roots.items()):
    pj = plugin_root / ".claude-plugin" / "plugin.json"
    rel = pj.relative_to(root)
    if not pj.exists():
        errors.append(f"{rel}: missing ({STALE_HINT})")
        continue
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    if data.get("name") != plugin_name:
        errors.append(f"{rel}: name must be '{plugin_name}'")
    if not KEBAB_RE.match(data.get("name", "")):
        errors.append(f"{rel}: name must be kebab-case")
    if not data.get("description"):
        errors.append(f"{rel}: description must be non-empty")
    declared = data.get("skills", [])
    declared = [declared] if isinstance(declared, str) else declared
    if sorted(declared) != expected_skills_dirs(plugin_root):
        errors.append(f"{rel}: stale skills dirs ({STALE_HINT})")

mp_file = repo_root / ".claude-plugin" / "marketplace.json"
if not mp_file.exists():
    errors.append(f".claude-plugin/marketplace.json: missing ({STALE_HINT})")
else:
    try:
        mp = json.loads(mp_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f".claude-plugin/marketplace.json: invalid JSON: {e}")
        mp = {}
    if mp:
        if mp.get("name") != "swissknifeman":
            errors.append(".claude-plugin/marketplace.json: name must be 'swissknifeman'")
        if not mp.get("owner", {}).get("name"):
            errors.append(".claude-plugin/marketplace.json: owner.name must be set")
        entries = mp.get("plugins", [])
        names = [p.get("name", "") for p in entries]
        if len(names) != len(set(names)):
            errors.append(".claude-plugin/marketplace.json: duplicate plugin names")
        # Supervised (non-bucket) plugins: there is NO plugin directory on disk - the plugin refers to
        # skills from DIFFERENT buckets via skills[] (source:"./"). Name mirroite config.CORE_PLUGIN;
        # the paths themselves skills[] check for existence below. (Double name - stdlib-only heredoc.)
        curated_plugin_names = ["core"]
        expected_names = list(plugin_roots) + sibling_plugin_names + curated_plugin_names
        if sorted(names) != sorted(expected_names):
            errors.append(
                f".claude-plugin/marketplace.json: plugins must match dirs on disk "
                f"({STALE_HINT})")
        for p in entries:
            src = p.get("source", "")
            # source-paths are relative to the repo root (./<package>/... or ./ for curated)
            if not (repo_root / src).is_dir():
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"source dir not found: {src}")
            if not p.get("description"):
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"description must be non-empty")
            # curated plugin: every path skills[] (from the root of the repo) must exist
            if p.get("name") in curated_plugin_names:
                for sk in (p.get("skills") or []):
                    if not (repo_root / sk).is_dir():
                        errors.append(
                            f".claude-plugin/marketplace.json: {p.get('name')}: "
                            f"skills path not found: {sk} ({STALE_HINT})")

# --- 7b. no skills nested inside a skill dir ---------------------------------
# Claude Code discovers a dir with SKILL.md as a leaf skill; SKILL.md deeper
# inside it is silently invisible to plugin discovery.
for skill_md in skill_files:
    d = skill_md.parent
    nested = [p for p in d.rglob("SKILL.md") if p != skill_md]
    for p in nested:
        errors.append(
            f"{p.relative_to(root)}: nested inside skill "
            f"'{d.relative_to(root)}' — invisible to plugin discovery; "
            f"flatten it (e.g. '{d.name}-{p.parent.name}' next to '{d.name}')")

# --- 8. skill-name uniqueness ------------------------------------------------
# Plugin namespace flattens per plugin: dup inside a bucket = error.
# Across buckets namespacing keeps it legal, but vendoring modes collide: warn.
by_bucket = {}
for skill_md in skill_files:
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "")
    if not name:
        continue
    bucket = skill_md.relative_to(root).parts[1] \
        if skill_md.relative_to(root).parts[0] == "skills" else "generate-skill"
    by_bucket.setdefault(bucket, {}).setdefault(name, []).append(
        str(skill_md.relative_to(root)))
seen_names = {}
for bucket, names in sorted(by_bucket.items()):
    for name, paths in sorted(names.items()):
        if len(paths) > 1:
            errors.append(
                f"duplicate skill name '{name}' in bucket '{bucket}': "
                f"{', '.join(paths)}")
        seen_names.setdefault(name, []).append(bucket)
for name, in_buckets in sorted(seen_names.items()):
    if len(in_buckets) > 1:
        warnings.append(
            f"skill name '{name}' appears in buckets {', '.join(in_buckets)} — "
            f"legal with plugin namespaces, collides in vendoring modes")

# --- 9. dependency graph (requires / produces_for) ---------------------------
# Edge names are frontmatter `name` values. Cycles are checked over `requires`
# only: an `A requires B` + `B produces_for A` pair is a normal complementary
# link, not a cycle.
graph_requires = {}
graph_produces = {}
name_to_rel = {}
for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name:
        continue
    name_to_rel.setdefault(name, str(rel))
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        raw = fm.get(key, "").strip()
        deps = parse_inline_list(raw)
        if raw and raw != "[]" and not deps:
            warnings.append(
                f"{rel}: {key} is set but not an inline list ('{raw}') — "
                f"use '[a, b]' syntax; multiline YAML lists are not parsed")
        store[name] = deps

all_names = set(graph_requires) | set(graph_produces)
for name in sorted(all_names):
    src = name_to_rel[name]
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        for dep in store.get(name, []):
            if dep == name:
                errors.append(f"{src}: {key} references itself")
            elif dep not in all_names:
                errors.append(f"{src}: {key} unknown skill '{dep}'")

# Cycle detection over `requires` (iterative DFS, white/grey/black colouring)
WHITE, GREY, BLACK = 0, 1, 2
colour = {n: WHITE for n in all_names}
for start in sorted(all_names):
    if colour[start] != WHITE:
        continue
    stack = [(start, iter(graph_requires.get(start, [])))]
    colour[start] = GREY
    path = [start]
    while stack:
        node, it = stack[-1]
        advanced = False
        for dep in it:
            if dep not in all_names:
                continue
            if colour[dep] == GREY:
                cycle = path[path.index(dep):] + [dep]
                errors.append(f"requires cycle: {' -> '.join(cycle)}")
            elif colour[dep] == WHITE:
                colour[dep] = GREY
                path.append(dep)
                stack.append((dep, iter(graph_requires.get(dep, []))))
                advanced = True
                break
        if not advanced:
            colour[node] = BLACK
            path.pop()
            stack.pop()

# --- 10. internal project skills (.claude/skills/) ---------------------------
# Internal registry development skills: NOT exported and NOT included in
# skills.json — lint softly (only name+description, without registry fields).
registry_names = set(seen_names)
# Local dev-skills can live in .claude/skills package, and in the ROOT MONOREPO
# (moved there for visibility from the root). Lint both places (standalone-safe).
_skill_roots = [root]
_mono = root.parent.parent          # packages/<pkg> → monorepo root
if _mono != root and (_mono / ".claude" / "skills").is_dir():
    _skill_roots.append(_mono)
_internal_skills = []
for _sr in _skill_roots:
    for _p in sorted(_sr.glob(".claude/skills/*/SKILL.md")):
        _internal_skills.append((_sr, _p))
for _sr, skill_md in _internal_skills:
    rel = skill_md.relative_to(_sr)
    fm = parse_frontmatter(skill_md)
    if fm is None:
        errors.append(f"{rel}: missing frontmatter block")
        continue
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name or not fm.get("description"):
        errors.append(f"{rel}: internal skill needs name + description")
        continue
    if not KEBAB_RE.match(name):
        errors.append(f"{rel}: name must be kebab-case")
    if name != skill_md.parent.name:
        errors.append(f"{rel}: name '{name}' must match dir '{skill_md.parent.name}'")
    if name in registry_names:
        warnings.append(
            f"{rel}: internal skill name '{name}' collides with a registry skill")

# --- 10b. slash-plugin commands skm (frontmatter) ----------------------------
# Command Person CLI: each skm/commands/*.md must have frontmatter with
# non-empty description (otherwise the command is without a signature in the menu Claude Code).
for cmd_md in sorted(root.glob("skm/commands/*.md")):
    rel = cmd_md.relative_to(root)
    fm = parse_frontmatter(cmd_md)
    if fm is None:
        errors.append(f"{rel}: missing/unterminated frontmatter block")
    elif not fm.get("description"):
        errors.append(f"{rel}: slash-command without non-empty description")

# --- 10c. agent `skills:` references resolve to registry skills --------------
# Bucket Agents (skills/<bucket>/agents/*.md) preload skills with native ones
# field `skills: [bucket:name, ...]` (Claude Code subagent preload). Everyone
# namespaced-element must point to a real registry skill - otherwise CC
# quietly lets him through with warning in debug-log.
registry_bn = set()
for skill_md in skill_files:
    fm = parse_frontmatter(skill_md)
    if not fm:
        continue
    b = (fm.get("bucket", "") or "").strip().strip('"').strip("'")
    n = (fm.get("name", "") or "").strip().strip('"').strip("'")
    if b and n:
        registry_bn.add(f"{b}:{n}")
for agent_md in sorted(root.glob("skills/*/agents/*.md")):
    rel = agent_md.relative_to(root)
    fm = parse_frontmatter(agent_md)
    if not fm:
        continue
    for entry in parse_inline_list(fm.get("skills", "")):
        if ":" not in entry:
            warnings.append(
                f"{rel}: skills-element '{entry}' without namespace (needed bucket:name)")
        elif entry not in registry_bn:
            errors.append(
                f"{rel}: skills-element '{entry}' does not resolve to the registry skill")

# --- report ----------------------------------------------------------------
for w in warnings:
    print(f"WARN: {w}")
for e in errors:
    print(f"ERROR: {e}")

if local_total:
    pct = 100 * local_with_evals // local_total
    print(f"evals coverage: {local_with_evals}/{local_total} local skills "
          f"have evals/ ({pct}%) — eval-first for new (skiller eval <skill>)")

checked = len(skill_files)
if errors:
    print(f"\n{checked} skills checked — {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1)
print(f"{checked} skills checked — all valid ({len(warnings)} warning(s))")
PY

# --- 11. CLI + shell scripts ---------------------------------------------------
[[ -x "$REPO_ROOT/bin/skiller" ]] || {
  echo "ERROR: bin/skiller missing or not executable" >&2; exit 1; }
for sh in "$REPO_ROOT/bin/skiller" "$REPO_ROOT/install.sh" \
          "$REPO_ROOT/sync.sh" "$REPO_ROOT"/scripts/*.sh; do
  bash -n "$sh" || { echo "ERROR: bash -n failed: $sh" >&2; exit 1; }
done
echo "CLI + shell scripts: syntax OK"

# --- 12. lib/skiller package + unit/integration tests --------------------------
[[ -d "$REPO_ROOT/lib/skiller" ]] || {
  echo "ERROR: lib/skiller package missing" >&2; exit 1; }
PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB" python3 -c "import skiller.cli" || {
  echo "ERROR: lib/skiller fails to import" >&2; exit 1; }
"$REPO_ROOT/scripts/test.sh" || { echo "ERROR: tests failed" >&2; exit 1; }

# --- 12b. registry drift-gate (skills.json/_index.md/manifests vs sources) ----
# Rebuilds the registry IN MEMORY and checks it against committed artifacts. Catches the quiet one
# drift (edit SKILL.md/buckets.json/neighboring plugin.json without `skiller registry`) —
# before validate only json.loads'or skills.json, without checking freshness. Gate for CI.
"$REPO_ROOT/bin/skiller" registry --check || {
  echo "ERROR: registry is out of date with respect to sources - run: skiller registry" >&2; exit 1; }

# --- 13. bucket-path drift lint (after the split php/frontend) --------------------
# Catches rotten links `php/<skill>` / `frontend/<skill>` in skill bodies and docks
# package, where <skill> by skills.json already lives in another bucket (laravel-*/frontend-*).
# Protects against path arch regression (audit). Only within-package (skiller); root
# docs/ — umbrella, out scope package.
python3 - "$REPO_ROOT" <<'PY'
import json, re, sys, pathlib
root = pathlib.Path(sys.argv[1])
sj = root / "skills.json"
if not sj.is_file():
    print("bucket-path lint: skills.json no - skip"); sys.exit(0)
skills = json.loads(sj.read_text(encoding="utf-8"))
skills = skills["skills"] if isinstance(skills, dict) else skills
name2bucket = {}
for s in skills:
    name2bucket.setdefault(s.get("name"), s.get("bucket"))
pat = re.compile(r'\b(php|frontend)/([a-z0-9][a-z0-9-]+)\b')
GENERATED = {"_index.md", "graph.md", "budget.md"}
stale = []
for base in ("skills", "docs"):
    for f in (root / base).rglob("*.md"):
        if f.name in GENERATED:
            continue
        for ln, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in pat.finditer(line):
                cur = name2bucket.get(m.group(2))
                if cur and cur != m.group(1):
                    stale.append(f"{f.relative_to(root)}:{ln}: {m.group(0)} → {cur}/{m.group(2)}")
if stale:
    print(f"ERROR: rotten bucket-paths after split ({len(stale)}):", file=sys.stderr)
    for s in stale[:40]:
        print("  " + s, file=sys.stderr)
    sys.exit(1)
print("bucket-path drift: no rotten php/<skill>|frontend/<skill> links")
PY

# --- 14. CORE resident budget (HARD gate) --------------------------------
# ⊕ tier-0 CORE_SKILLS is loaded into EVERY request - gate against silent kernel growth above
# target (resident_budget_target in core-policy.json). --strict = non-zero code when
# exceeded. Was here before `|| true` (soft, contrary to the same comment) — honestly
# made by a real gate: comment promised strict — now it works.
bash "$REPO_ROOT/bin/skiller" budget --check-core --strict || {
  echo "ERROR: CORE resident budget exceeded - shorten descriptions/core skills (skiller budget)" >&2
  exit 1; }

# --- 16. framework canon freshness (Skiller docs ⇄ host agent-pack versions) ------
# Cross-package gate: lives in the host repository (scripts/agent-framework-freshness.py,
# hygiene CI), not in this package.

# --- 17. WARN: listing of profile detection against fallback budget Codex ---
# Gate WARN, not ERROR: structural brute force is a known distribution composition problem,
# not hygienic, red CI doesn't fix it (see budget.py CODEX_LISTING_FALLBACK_CHARS). Profile,
# whose listing exceeds the fallback budget Codex 8 000 character, prints number and profile; decision
# (narrowing/skillOverrides/accepted degradation) — owner's decision, not this script.
# Python himself is calling CLI subprocess (and does not read it stdout via pipe in `python3 -
# <<heredoc`) — conflict: heredoc and pipe feed one at a time stdin, second silently
# is lost (python reads YOUR script from heredoc, and not JSON from pipe).
python3 - "$REPO_ROOT" <<'PY'
import json, subprocess, sys

repo_root = sys.argv[1]
result = subprocess.run(["bash", f"{repo_root}/bin/skiller", "budget",
                        "--profiles", "--json"], capture_output=True, text=True)
try:
    rows = json.loads(result.stdout)
except json.JSONDecodeError:
    print("detection listing Codex: missing (--profiles --json did not produce valid output)")
    sys.exit(0)

over = [r for r in rows if r["codex"]["over"]]
if over:
    print(f"WARN: {len(over)} profile(to her) listings exceed fallback detection budget "
          f"Codex (8 000 char) — structural search:")
    for r in over:
        c = r["codex"]
        print(f"  {r['profile']}: {c['raw']} char (×{c['raw'] / c['budget']:.1f})")
else:
    print("detection listing Codex: all profiles fit within the fallback budget of 8,000 characters")
PY

# --- 18. Codex publication consumer-acceptance -----------------------
# Isolated round-trip alive `codex` CLI: marketplace add → plugin list/add →
# clean-consumer discovery in temp CODEX_HOME — what the static does NOT check
# diagram (`test_codex_publication.py`). Azguard, 2026-07-21: batch GREEN was,
# consumer path — no. Explicit discrimination skip/GREEN/RED in the output - "gate not
# ran" and "gate passed" are not the same thing. The expected inventory comes from the
# host config (default command plugins + sibling plugin dirs); without a host the
# gate has nothing to compare and is skipped explicitly.
_host_rc=0
PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB" python3 -c \
  'import sys; from pathlib import Path; from skiller.host import load_host; sys.exit(0 if load_host(Path(sys.argv[1])).default_command_plugins else 3)' \
  "$REPO_ROOT" || _host_rc=$?
if [ "$_host_rc" -ne 0 ] && [ "$_host_rc" -ne 3 ]; then
  echo "ERROR: Codex publication consumer-acceptance gate - host config unreadable" >&2
  exit 1
elif [ "$_host_rc" -eq 3 ]; then
  echo "SKIP: Codex publication consumer-acceptance gate - no host config (standalone)"
elif ! command -v codex >/dev/null 2>&1; then
  echo "SKIP: Codex publication consumer-acceptance gate - binary 'codex' not found in PATH (gate was NOT driven, do not count as GREEN)"
else
  codex_version="$(codex --version 2>/dev/null || echo unknown)"
  _codex_gate_log="$(mktemp)"
  if (cd "$REPO_ROOT" && PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -m unittest tests.test_codex_consumer_acceptance -v) > "$_codex_gate_log" 2>&1; then
    echo "Codex publication consumer-acceptance: GREEN (codex ${codex_version})"
  else
    cat "$_codex_gate_log" >&2
    echo "ERROR: Codex publication consumer-acceptance gate red (codex ${codex_version})" >&2
    rm -f "$_codex_gate_log"
    exit 1
  fi
  rm -f "$_codex_gate_log"
fi
