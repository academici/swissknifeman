"""Explicit project plugin activation and read-only native Codex discovery."""
import json
import copy
import os
from pathlib import Path
import re
import subprocess
import tempfile

from ..artifacts.lock import _contained_target, _writer_guard
from ..config.toml import loads as toml_loads
from ..util.io import atomic_write_text
from . import MARKETPLACE

SUFFIX = "@" + MARKETPLACE


def codex_home(env):
    return Path(os.environ.get("CODEX_HOME", str(env.home / ".codex")))


def _read(path):
    text = path.read_bytes().decode("utf-8") if path.exists() else ""
    return text, toml_loads(text, source=str(path))


def plan_selection(env, target, selected, known):
    """Patch only plugin enabled scalars; reject layouts we cannot preserve exactly.

    Parsing and rendering complete before Connect mutates any delivery surface.
    The caller explicitly owns the Swissknifeman activation selection, while all
    other settings, plugin fields and comments remain byte-for-byte unchanged.
    """
    path = _contained_target(Path(target), ".codex/config.toml")
    before, data = _read(path)
    _, user = _read(codex_home(env) / "config.toml")
    names = set(known) | set(selected)
    for layer in (user, data):
        plugins = layer.get("plugins", {})
        if not isinstance(plugins, dict):
            raise ValueError("CODEX_SELECTION_LAYOUT: plugins must be a table")
        names.update(key[:-len(SUFFIX)] for key in plugins if key.endswith(SUFFIX))
    lines = before.splitlines(keepends=True)
    sections = {}
    headers = []
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("["):
            continue
        parsed = toml_loads(line, source=str(path))
        headers.append(index)
        plugins = parsed.get("plugins", {})
        if isinstance(plugins, dict) and len(plugins) == 1:
            key, value = next(iter(plugins.items()))
            if key.endswith(SUFFIX) and value == {}:
                sections[key] = index
    edits, additions = [], []
    for name in sorted(names):
        key = name + SUFFIX
        value = name in selected
        literal = "true" if value else "false"
        existing = data.get("plugins", {}).get(key)
        if existing is not None:
            if not isinstance(existing, dict) or key not in sections:
                raise ValueError("CODEX_SELECTION_LAYOUT: use a dedicated [plugins.\"" + key + "\"] table")
            start = sections[key]
            end = next((i for i in headers if i > start), len(lines))
            matches = []
            for i in range(start + 1, end):
                match = re.fullmatch(r'(\s*(?:enabled|"enabled"|\x27enabled\x27)\s*=\s*)(true|false)(\s*(?:#[^\r\n]*)?)(\r?\n)?', lines[i])
                if match:
                    matches.append((i, match))
            if "enabled" in existing:
                if len(matches) != 1 or not isinstance(existing["enabled"], bool):
                    raise ValueError("CODEX_SELECTION_LAYOUT: unsupported enabled scalar for " + key)
                i, match = matches[0]
                edits.append((i, match[1] + literal + match[3] + (match[4] or "")))
            else:
                edits.append((start, lines[start] + ("" if lines[start].endswith("\n") else "\n")
                              + "enabled = " + literal + "\n"))
        else:
            additions.append("[plugins." + json.dumps(key) + "]\nenabled = " + literal + "\n")
    for index, replacement in edits:
        lines[index] = replacement
    after = "".join(lines)
    if additions:
        after += (("\n" if after.endswith("\n") else "\n\n") if after else "") + "\n".join(additions)
    parsed = toml_loads(after, source=str(path))
    expected = copy.deepcopy(data)
    for name in names:
        expected.setdefault("plugins", {}).setdefault(name + SUFFIX, {})["enabled"] = name in selected
    if parsed != expected:
        raise ValueError("CODEX_SELECTION_RENDER: changes extend beyond plugin activation")
    return {"path": path, "before": before, "after": after, "existed": path.exists(),
            "selected": sorted(selected)}


def apply_selection(target, plan, *, dry_run=False):
    if plan["before"] == plan["after"]:
        return False
    if dry_run:
        print(f"[dry-run] Codex native selection → {plan['path']}")
        return True
    with _writer_guard(Path(target)):
        path = _contained_target(Path(target), ".codex/config.toml")
        current, _ = _read(path)
        if current != plan["before"] or path.exists() != plan["existed"]:
            raise ValueError("CODEX_SELECTION_PREIMAGE_CHANGED: " + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix="config.toml.",
                                             suffix=".bak", delete=False) as backup:
                backup.write(path.read_bytes())
        atomic_write_text(path, plan["after"])
    print(f"Codex native selection: {len(plan['selected'])} plugins → {path}")
    return True


def native_inventory(env, target, *, runner=subprocess.run):
    """Ask the installed CLI what this cwd discovers; bundles alone prove nothing."""
    process_env = dict(os.environ, CODEX_HOME=str(codex_home(env)))
    try:
        prompt = runner(["codex", "debug", "prompt-input"], cwd=str(target),
                        env=process_env, capture_output=True, text=True, timeout=30, check=False)
        if prompt.returncode:
            raise ValueError("prompt-input: " + prompt.stderr.strip()[:300])
        messages = json.loads(prompt.stdout)
        texts = [block.get("text", "") for message in messages
                 for block in message.get("content", [])
                 if "<skills_instructions>" in block.get("text", "")]
        if not texts:
            raise ValueError("prompt-input has no skills_instructions")
        names, native_names, paths, enabled = set(), set(), {}, set()
        cache = (codex_home(env) / "plugins/cache/swissknifeman").resolve()
        for text in texts:
            roots = dict(re.findall(r"^- `(r\d+)` = `([^`]+)`$", text, re.MULTILINE))
            for identity, reference in re.findall(r"^- (\S+): .*\(file: (.+)\)$", text, re.MULTILINE):
                name = identity.rsplit(":", 1)[-1]
                alias = re.fullmatch(r"(r\d+)(/.*)?", reference)
                if alias:
                    if alias[1] not in roots:
                        raise ValueError("unknown skill root alias " + alias[1])
                    reference = str(Path(roots[alias[1]]) / (alias[2] or "").lstrip("/"))
                path = Path(reference)
                names.add(name)
                paths.setdefault(name, []).append(str(path))
                if path.resolve().is_relative_to(cache) and ":" in identity:
                    native_names.add(name)
                    enabled.add(path.resolve().relative_to(cache).parts[0])
        return {"ok": True, "names": names, "native_names": native_names, "paths": paths,
                "enabled": sorted(enabled),
                "notes": []}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        return {"ok": False, "names": set(), "native_names": set(), "paths": {}, "enabled": [],
                "notes": [f"Codex native discovery unavailable: {error}"]}
