"""maind code-graph — default provider.serena/project.yml + code graph policy resolver.

When a project has a code graph enabled (field `code:true`, legacy-alias `graphify:true`), maind puts
him starting `.serena/project.yml`: language by project type + ignores + initial_prompt. ALL policies
(ignores vendor/packages, engine command, prompts) is taken from the section `code_graph` config
(.maind.example.json), and not hardcoded - there is only a resolver with per-project override and
legacy-alias `graphify_*` → `code_*`.

We write.serena/project.yml ONLY if the file does not exist yet: after the first activation Serena owns it herself
(appends the full template) — do not clobber. When turned on, we optionally warm up the index in the background
(pre_index) — so that the first call in the session does not wait. stdlib-only; external Serena — via subprocess."""
import os
import shutil
import subprocess
from pathlib import Path

from .common import atomic_write_text, warn
from .constants import CODE_GRAPH_DEFAULTS, SERENA_SCHEMA_FIELDS, SERENA_SRC

SERENA_CONFIG = Path(".serena") / "project.yml"


# ── code-graph policy: config + per-project override (alias graphify_* → code_*) ────
def settings(config):
    """Merged code-graph policy (merge_defaults has already cast CODE_GRAPH_DEFAULTS)."""
    return config.get("code_graph") or dict(CODE_GRAPH_DEFAULTS)


def _proj(project, *keys, default=None):
    """First specified from per-project keys (new code_*, then legacy graphify_*)."""
    for k in keys:
        if project.get(k) is not None:
            return project[k]
    return default


def enabled(project, st):
    return bool(_proj(project, "code", "graphify", default=st.get("enabled_default", False)))


def command(project, st):
    return _proj(project, "code_command", "graphify_command", default=st["command"])


def cmd_args(project, st):
    return _proj(project, "code_args", "graphify_args", default=st["args"])


def server_name(project, st):
    return _proj(project, "code_server_name", "graphify_server_name", default=st["server_name"])


def is_engine_serena(project, st):
    """The engine is default Serena (and not a third party override MCP)? Only for him
    makes sense.serena/project.yml."""
    return (command(project, st) == st["command"]
            and server_name(project, st) == st["server_name"])


def is_workspace(project, path):
    """Workspace-mode (single graph with local packages): explicit flag code_workspace/
    graphify_workspace, otherwise auto - there is a directory packages/ (monorepo or consumer with
    sub-linked first-party packages; default otherwise hides their source)."""
    flag = _proj(project, "code_workspace", "graphify_workspace")
    if flag is not None:
        return bool(flag)
    return (path / "packages").is_dir()


def _infer_language(project, path, st):
    """Language(and) for Serena. Priority: per-project override (code_language(s), legacy
    graphify_language) → by project type (language_by_type) → by manifest → None (Serena
    autodetect itself). Returns str | list str | None. Override is needed for mixed
    repo: type sets ONE language (e.g. node-package→typescript), and python-monorepo with
    docs on TS code basically python — here it is fixed without editing the general constants."""
    override = _proj(project, "code_language", "code_languages", "graphify_language")
    if override:
        return override
    lang = (st.get("language_by_type") or {}).get(project.get("type"))
    if lang:
        return lang
    if (path / "composer.json").is_file():
        return "php"
    if (path / "package.json").is_file():
        return "typescript"
    return None


def render_project_yaml(name, language, ignores, initial_prompt, gitignore=True):
    """Fully valid .serena/project.yml for the current scheme Serena.
    language: str | list str | None.

    Serena `_from_dict` requires without `.get()` only `project_name`/`language_servers`
    (FIELDS_WITHOUT_DEFAULTS pinned version, constants.SERENA_SCHEMA_FIELDS) — others
    keys (symbol_info_budget, ignored_paths, fixed_tools, excluded_tools,
    included_optional_tools, read_only, ignore_all_files_in_gitignore, initial_prompt,
    encoding, added_modes, default_modes) have defaults (`data.setdefault`) and their absence
    does NOT give KeyError. We print the full set ourselves - for the sake of clarity of the config, and not because
    upstream requires this. Defaults are reconciled with serena/resources/project.template.yml.
    `language_servers` is always present (empty list for unrecognized language -
    standalone-type + empty repo)."""
    langs = [language] if isinstance(language, str) else (language or [])
    lines = [f'project_name: "{name}"']
    if langs:
        lines += ["language_servers:"] + [f"  - {lang}" for lang in langs]
    else:
        lines += ["language_servers: []"]  # Serena will automatically detect the language upon activation (without KeyError)
    lines += ['encoding: "utf-8"',
              f"ignore_all_files_in_gitignore: {'true' if gitignore else 'false'}",
              "ignored_paths:"]
    # Human Task projections are never code-graph input, even when gitignored files are indexed.
    lines += [f'  - "{p}"' for p in dict.fromkeys([*ignores, "plans/**/views/**", "plans/**/context/**", "plans/**/*.md"])]
    lines += ["read_only: false",
              # required for the current Serena — defaults from her project.template.yml:
              "excluded_tools: []",
              "included_optional_tools: []",
              "fixed_tools: []",
              "default_modes:",
              "added_modes:",
              "symbol_info_budget:",
              f'initial_prompt: "{initial_prompt}"', ""]
    return "\n".join(lines)


def _extract_pin(src):
    """Pin shape `git+URL@REF` → REF (tag or full SHA, D110 — both are legal); None, if
    source not pinned (no '@' or empty tail)."""
    if not src or "@" not in src:
        return None
    ref = src.rsplit("@", 1)[1]
    return ref or None


def _pin_from_args(args):
    """REF from `--from <SRC>` in the list args serena-commands (args/index_args config)."""
    for i, a in enumerate(args or []):
        if a == "--from" and i + 1 < len(args):
            return _extract_pin(args[i + 1])
    return None


def check_schema_connectivity(config):
    """Connectivity gate (D111, P5.4): version Serena, which the fleet kicks at
    (`constants.SERENA_SRC` + `code_graph.args`/`index_args` config), is obliged to demand the same
    diagram `.serena/project.yml`, which actually prints `render_project_yaml`. Offline and
    deterministic: compares tree facts (no network, no uvx). does NOT fix
    discrepancy - just names it; solution (bump pin or rollback template) — for
    owner (D111). Returns a list of human-readable discrepancies; empty list - gate
    green."""
    st = settings(config)
    issues = []

    src_pin = _extract_pin(SERENA_SRC)
    args_pin = _pin_from_args(st.get("args"))
    index_pin = _pin_from_args(st.get("index_args"))

    if src_pin is None:
        issues.append(
            f"pin missing: constants.SERENA_SRC does not contain '@REF' ({SERENA_SRC!r})")
    if st.get("args") and args_pin is None:
        issues.append(
            "pin missing: code_graph.args does not contain a config '@REF' in '--from'")
    if st.get("index_args") and index_pin is None:
        issues.append(
            "pin missing: code_graph.index_args does not contain a config '@REF' in '--from'")

    pins = {p for p in (src_pin, args_pin, index_pin) if p is not None}
    if len(pins) > 1:
        issues.append(
            "pins dispersed: constants.SERENA_SRC={!r}, code_graph.args={!r}, "
            "code_graph.index_args={!r} — edit both places (constants.py and config.json) "
            "with one seam".format(src_pin, args_pin, index_pin))

    # We take the keys from the REAL renderer output (not from his copy here) — otherwise the gate started
    # would check their copy of the truth, not the real one (Code Guidance «Anti-self-deception», P5.4).
    sample = render_project_yaml("_schema_probe", None, [], "", gitignore=True)
    rendered_keys = {line.split(":", 1)[0].strip()
                      for line in sample.splitlines()
                      if line and not line[0].isspace() and ":" in line}
    # Only MISSING required keys - discrepancy; optional extra keys
    # renderer (e.g. project_name) out FIELDS_WITHOUT_DEFAULTS do not count (Scope Excluded).
    missing = set(SERENA_SCHEMA_FIELDS) - rendered_keys
    if missing:
        issues.append(
            "scheme diverged: constants.SERENA_SCHEMA_FIELDS (waiting for pin {!r}) requires "
            "{}, which codegraph.render_project_yaml DOES NOT print (actually prints {}) — "
            "correct constants.py SERENA_SCHEMA_FIELDS or codegraph.py render_project_yaml, "
            "until both places match".format(
                SERENA_SRC, sorted(missing), sorted(rendered_keys)))

    return issues


def _maybe_pre_index(st, project, path):
    """Background warming-indexing Serena (detach, does not block). Quiet skip, if disabled
    in the config or the engine is unavailable."""
    if not st.get("pre_index"):
        return
    cmd = command(project, st)
    if shutil.which(cmd) is None:
        return
    argv = [cmd] + [a.replace("{root}", str(path)) for a in st.get("index_args", [])]
    try:
        subprocess.Popen(argv, cwd=str(path), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as e:
        warn(f"pre-index '{project['id']}' did not start: {e}")


def apply_serena_config(env, config, project, mode, dry):
    """Put start .serena/project.yml, if the code graph is enabled (Serena) and there is no file."""
    pid = project["id"]
    st = settings(config)
    if not enabled(project, st):
        return {"provisioner": "code-graph", "id": pid, "status": "skip",
                "changed": False, "state": "disabled", "detail": "code graph disabled"}
    if not is_engine_serena(project, st):
        return {"provisioner": "code-graph", "id": pid, "status": "skip",
                "changed": False, "state": "custom", "detail": "engine not Serena"}
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return {"provisioner": "code-graph", "id": pid, "status": "skip",
                "changed": False, "state": "absent", "detail": "no path"}
    target = path / SERENA_CONFIG
    if target.exists():  # owns the file after activation Serena — not overwritten
        return {"provisioner": "code-graph", "id": pid, "status": "ok",
                "changed": False, "state": "present", "detail": str(SERENA_CONFIG)}
    ws = is_workspace(project, path)
    override = _proj(project, "code_ignores")
    ignores = override or (st["workspace_ignores"] if ws else st["ignores"])
    prompt = st["workspace_prompt"] if ws else st["initial_prompt"]
    content = render_project_yaml(pid, _infer_language(project, path, st),
                                  ignores, prompt, gitignore=not ws)
    if not dry:
        atomic_write_text(target, content)
        _maybe_pre_index(st, project, path)
    return {"provisioner": "code-graph", "id": pid,
            "status": "dry" if dry else "ok", "changed": not dry,
            "state": "absent", "detail": str(SERENA_CONFIG)}
