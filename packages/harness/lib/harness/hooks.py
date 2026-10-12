"""Internal documentation."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from aicore.artifacts.artifact import (
    ArtifactAdapterIdentity,
    ArtifactRenderRequest,
    ArtifactSource,
    ArtifactTarget,
    canonical_json_bytes,
    plan_artifact_render,
    sha256_digest,
)
from aicore.artifacts.lock import (
    LOCK_RELATIVE_PATH,
    apply_plan,
    artifact_dry_run,
    plan_artifact_lock,
    render_artifact_projection,
)
from aicore.config import ConfigError, edit_layer_file
from aicore.state import project_config_file
from aicore.provider.values import DiagnosticSeverity, ProviderId

from aicore.util.cli import parse_flags
from aicore.util.term import die, warn
from . import hooks_env
from .profiles import (HarnessDiagnostic, ProfileCatalog, default_catalog_path,
                       load_catalog)
from .settings import (add_hook, load_settings, set_setting_key, set_swissknife,
                       write_json, write_text)

AA_MODES = ("strict", "permissive", "bypass", "off")
MEM_MODES = ("maind", "manual", "file", "federation", "agentmemory", "off")
MAIND_MEMORY_MODES = ("maind", "manual")
ROUTER_MODES = ("propose", "auto_dispatch", "off")
RUNREPORT_MODES = ("on", "off")
PACKGUARD_MODES = ("off", "warn", "strict")
PLANREGEN_MODES = ("off", "on")
CHANGELOGGATE_MODES = ("off", "warn", "strict")
PLANSDIR_DEFAULT = "plans"
STATUSLINE_MODES = ("context", "off")

STATUSLINE_VALUE = {"type": "command",
                    "command": "~/.claude/statusline/context-notify.sh"}


@dataclass(frozen=True)
class LifecycleRequest:
    """A selected common lifecycle/context intent; native details stay in adapters."""
    surface_id: str
    required: bool = False


@dataclass(frozen=True)
class LifecycleBinding:
    surface_id: str
    support_level: str
    activation: str
    event: str = ""
    matcher: str = ""
    handler: str = ""
    kill_switch: str = ""
    diagnostic_code: str = ""


@dataclass(frozen=True)
class LifecycleRenderPlan:
    provider_id: ProviderId
    bindings: tuple[LifecycleBinding, ...]
    diagnostics: tuple[HarnessDiagnostic, ...]

    @property
    def green(self):
        return not any(item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics)


_CODEX_HOOK_ADAPTER_VERSION = "1.1.1"
_CODEX_CAPTURE_ADAPTER_VERSION = "1.0.0"
_LIFECYCLE_KINDS = frozenset(("lifecycle", "context", "security"))
_D104_CODEX_HOOKS_TARGET = ".codex/hooks.json"


@dataclass(frozen=True)
class CodexLifecycleFragment:
    """P5-owned observer input for the D104 P6 composition caller."""
    target_path: str
    event: str
    group: dict
    handler_bytes: bytes


def _claude_lifecycle_bindings():
    """Compatibility projection only; raw Claude registrations are never rendered for Codex."""
    return {
        "lifecycle.auto-approval": LifecycleBinding("lifecycle.auto-approval", "native", "project-settings", "PreToolUse", "Bash|ExitPlanMode", "~/.claude/hooks/auto-approve/auto-approve.sh", "MODE=off"),
        "lifecycle.memory": LifecycleBinding("lifecycle.memory", "native", "global-hook-plus-project-config", handler="~/.claude/hooks/memory/memory.sh", kill_switch="MODE=off"),
        "lifecycle.notification": LifecycleBinding("lifecycle.notification", "native", "global-hook", handler="~/.claude/hooks/notify/notify.sh"),
        "lifecycle.command-log": LifecycleBinding("lifecycle.command-log", "native", "global-hook", "PreToolUse", "Bash", "~/.claude/hooks/log-bash-command.sh"),
        "lifecycle.tool-telemetry": LifecycleBinding("lifecycle.tool-telemetry", "unsupported", "none", diagnostic_code="HARNESS_ACTIVATION_UNSUPPORTED"),
        "lifecycle.router": LifecycleBinding("lifecycle.router", "native", "project-settings", "UserPromptSubmit|SessionStart", "", "python3 ~/.claude/hooks/agent-router/router.py", "POLICY=off"),
        "lifecycle.run-report": LifecycleBinding("lifecycle.run-report", "native", "project-settings", "SessionEnd", "", "python3 ~/.claude/hooks/run-report/run-report.py", "ENABLED=off"),
        "lifecycle.pack-guard": LifecycleBinding("lifecycle.pack-guard", "native", "project-settings", "PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "python3 ~/.claude/hooks/pack-guard/pack-guard.py", "MODE=off"),
        "lifecycle.changelog-gate": LifecycleBinding("lifecycle.changelog-gate", "native", "project-settings", "PreToolUse", "Bash", "python3 ~/.claude/hooks/changelog-gate/changelog-gate.py", "MODE=off"),
        "lifecycle.review-gate": LifecycleBinding("lifecycle.review-gate", "native", "global-hook", "SubagentStop", "", "~/.claude/hooks/review-gate/review-gate.sh"),
        "lifecycle.daemon-safety": LifecycleBinding("lifecycle.daemon-safety", "native", "global-hook", "PreToolUse", "Bash", "~/.claude/hooks/daemon-safety/block-daemon-ops.sh"),
        "lifecycle.git-guardrails": LifecycleBinding("lifecycle.git-guardrails", "unsupported", "none", diagnostic_code="HARNESS_ACTIVATION_UNSUPPORTED"),
        "lifecycle.plan-guard": LifecycleBinding("lifecycle.plan-guard", "native", "project-settings", "PreToolUse", "Edit|Write|MultiEdit", "python3 ~/.claude/hooks/plan-guard/plan-guard.py", "MODE=off"),
        "lifecycle.plan-regen": LifecycleBinding("lifecycle.plan-regen", "native", "project-settings", "PostToolUse", "Edit|Write|MultiEdit", "python3 ~/.claude/hooks/plan-regen/plan-regen.py", "MODE=off"),
        "security.safe-dirs": LifecycleBinding("security.safe-dirs", "native", "embedded-in-auto-approval", "PreToolUse", "Bash", "~/.claude/hooks/auto-approve/lib/safedirs.py"),
        "context.observer": LifecycleBinding("context.observer", "unsupported", "none", diagnostic_code="HARNESS_ACTIVATION_UNSUPPORTED"),
        "context.output-style": LifecycleBinding("context.output-style", "native", "new-session", handler="outputStyle", kill_switch="outputStyle=off"),
        "context.plans-directory": LifecycleBinding("context.plans-directory", "native", "project-settings", handler="plansDirectory", kill_switch="plansDirectory=off"),
    }


def _load_provider_lifecycle_bindings(path, *, provider_id: str):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or set(value) != {"provider_id", "bindings"}
            or value["provider_id"] != provider_id):
        raise ValueError("HARNESS_MAPPING_MISSING")
    rows = value["bindings"]
    if not isinstance(rows, list):
        raise ValueError("HARNESS_MAPPING_MISSING")
    result = {}
    fields = {"surface_id", "support_level", "activation", "event", "matcher", "handler", "kill_switch", "diagnostic_code"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("HARNESS_MAPPING_MISSING")
        binding = LifecycleBinding(**row)
        if (binding.surface_id in result
                or binding.support_level not in {"hook-native", "config-native", "unsupported"}
                or binding.support_level == "hook-native" and (not binding.event or not binding.handler)
                or binding.support_level != "hook-native" and (binding.event or binding.matcher or binding.handler)):
            raise ValueError("HARNESS_MAPPING_MISSING")
        result[binding.surface_id] = binding
    return result


def _load_codex_lifecycle_bindings(path):
    return _load_provider_lifecycle_bindings(path, provider_id="codex")


def _load_cursor_lifecycle_bindings(path):
    return _load_provider_lifecycle_bindings(path, provider_id="cursor")


def plan_lifecycle(catalog: ProfileCatalog, *, provider_id: ProviderId,
                   requests: tuple[LifecycleRequest, ...], trusted: bool,
                   codex_bindings_path: Path | None = None,
                   cursor_bindings_path: Path | None = None) -> LifecycleRenderPlan:
    """Resolve native bindings and diagnostics before any registration artifact is produced."""
    if not isinstance(catalog, ProfileCatalog) or not isinstance(provider_id, ProviderId):
        raise TypeError("catalog and provider_id are required")
    if len({request.surface_id for request in requests}) != len(requests):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    if provider_id is ProviderId.CLAUDE_CODE:
        bindings = _claude_lifecycle_bindings()
    else:
        path = cursor_bindings_path or codex_bindings_path
        bindings = (_load_provider_lifecycle_bindings(path, provider_id=provider_id.value)
                    if path else None)
    if bindings is None:
        raise ValueError("HARNESS_MAPPING_MISSING")
    valid = {surface.id for surface in catalog.surfaces if surface.kind in _LIFECYCLE_KINDS}
    rendered, diagnostics = [], []
    for request in requests:
        if request.surface_id not in valid:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        binding = bindings.get(request.surface_id)
        if binding is None:
            raise ValueError("HARNESS_MAPPING_MISSING")
        rendered.append(binding)
        if binding.support_level == "unsupported":
            diagnostics.append(_lifecycle_diagnostic(binding.diagnostic_code, provider_id, request))
        elif binding.activation.startswith("trusted-project") and not trusted:
            diagnostics.append(_lifecycle_diagnostic("HARNESS_TRUST_REQUIRED", provider_id, request))
    return LifecycleRenderPlan(provider_id, tuple(rendered), tuple(sorted(diagnostics)))


def _lifecycle_diagnostic(code, provider_id, request):
    severity = DiagnosticSeverity.ERROR if request.required else DiagnosticSeverity.WARNING
    return HarnessDiagnostic(severity, code, provider_id, "", request.surface_id,
                             path="/lifecycle", required=request.required,
                             message="native lifecycle activation is unavailable",
                             next_action="select a supported provider binding")


_CODEX_EVENT_REQUIRED_FIELDS = {
    "SessionStart": ("source",),
    "SessionEnd": ("reason",),
    "UserPromptSubmit": ("prompt",),
    "PreToolUse": ("tool_name", "tool_input"),
    "PostToolUse": ("tool_name", "tool_input"),
    "PermissionRequest": ("tool_name", "tool_input"),
    "SubagentStop": ("agent_type",),
    "Stop": ("stop_hook_active", "last_assistant_message"),
}


def adapt_codex_hook_payload(binding: LifecycleBinding, payload: dict) -> dict:
    """Internal documentation."""
    if (not isinstance(binding, LifecycleBinding) or not isinstance(payload, dict)
            or binding.support_level != "hook-native"):
        raise TypeError("binding and payload are required")
    required = {"session_id", "cwd", "hook_event_name", "model"}
    if binding.event == "SessionStart":
        required.add("permission_mode")
    event_fields = _CODEX_EVENT_REQUIRED_FIELDS.get(binding.event, ())
    required.update(event_fields)
    if not required.issubset(payload) or payload["hook_event_name"] != binding.event:
        raise ValueError("HARNESS_MAPPING_MISSING")
    envelope = {"surface_id": binding.surface_id, "event": binding.event,
                "session_id": payload["session_id"], "cwd": payload["cwd"],
                "turn_id": payload.get("turn_id", ""),
                "permission_mode": payload.get("permission_mode", "")}
    for field in event_fields:
        envelope[field] = payload[field]
    return envelope


_CLAUDE_SHAPED_HOOK_DIRS = {
    ProviderId.CODEX: ".codex",
    ProviderId.GROK: ".grok",
}


def claude_shaped_hook_paths(provider_id: ProviderId) -> tuple[str, str]:
    """Return ``(document, handler)`` for a Claude-shaped hook bundle.

    Codex loads one ``.codex/hooks.json``. Grok loads every ``.grok/hooks/*.json``
    and ignores a sibling ``.grok/hooks.json``.
    """
    state_dir = _CLAUDE_SHAPED_HOOK_DIRS.get(provider_id)
    if state_dir is None:
        raise ValueError("HARNESS_MAPPING_MISSING")
    handler = f"{state_dir}/hooks/lifecycle.py"
    if provider_id is ProviderId.GROK:
        return f"{state_dir}/hooks/swissknifeman.json", handler
    return f"{state_dir}/hooks.json", handler


def render_codex_hooks(plan: LifecycleRenderPlan) -> bytes:
    """Render Claude-shaped hooks.json; Codex and Grok share this wire format."""
    state_dir = _CLAUDE_SHAPED_HOOK_DIRS.get(plan.provider_id)
    if state_dir is None or not plan.green:
        raise ValueError("cannot render refused lifecycle plan")
    hooks = {}
    for binding in plan.bindings:
        if binding.support_level != "hook-native":
            continue
        group = {"hooks": [{"type": "command", "command":
                 f'python3 "$(git rev-parse --show-toplevel)/{state_dir}/hooks/lifecycle.py" --surface {binding.surface_id}'}]}
        if binding.matcher:
            group["matcher"] = binding.matcher
        hooks.setdefault(binding.event, []).append(group)
    return (json.dumps({"description": "Managed provider-native lifecycle hooks.", "hooks": hooks},
                       ensure_ascii=False, indent=2) + "\n").encode("utf-8")


_CURSOR_HANDLER_COMMAND_PREFIX = ('python3 "${CURSOR_PROJECT_DIR:-.}/.cursor/hooks/lifecycle.py" '
                                  '--surface ')
_CURSOR_ENFORCEMENT_SURFACES = frozenset((
    "security.safe-dirs", "lifecycle.daemon-safety", "lifecycle.git-guardrails",
    "lifecycle.changelog-gate", "lifecycle.pack-guard", "lifecycle.plan-guard",
    "lifecycle.review-gate",
))


def _cursor_loop_limit(event):
    if event in {"stop", "subagentStop"}:
        return 3
    return None


def _cursor_entry_from_binding(binding):
    entry = {"command": _CURSOR_HANDLER_COMMAND_PREFIX + binding.surface_id}
    if binding.matcher:
        entry["matcher"] = binding.matcher
    if binding.surface_id in _CURSOR_ENFORCEMENT_SURFACES:
        entry["failClosed"] = True
    loop_limit = _cursor_loop_limit(binding.event)
    if loop_limit is not None:
        entry["loop_limit"] = loop_limit
    return entry


def _cursor_normalize_entry(raw):
    if not isinstance(raw, dict):
        return None
    if "hooks" in raw:
        hooks = raw.get("hooks")
        if (set(raw) - {"hooks", "matcher"} or not isinstance(hooks, list) or len(hooks) != 1
                or not isinstance(hooks[0], dict)):
            return None
        value = dict(hooks[0])
        if "matcher" in raw and "matcher" not in value and isinstance(raw["matcher"], str):
            value["matcher"] = raw["matcher"]
        return value
    return dict(raw)


def _cursor_is_managed_entry(entry):
    command = entry.get("command")
    return isinstance(command, str) and command.startswith(_CURSOR_HANDLER_COMMAND_PREFIX)


def _cursor_collect_preserved(existing_document):
    if existing_document is None:
        return [], {}
    if not isinstance(existing_document, dict):
        raise ValueError("HARNESS_CURSOR_HOOKS_INVALID")
    raw_hooks = existing_document.get("hooks", {})
    if not isinstance(raw_hooks, dict):
        raise ValueError("HARNESS_CURSOR_HOOKS_INVALID")
    event_order, preserved = [], {}
    for event, entries in raw_hooks.items():
        if not isinstance(event, str) or not isinstance(entries, list):
            raise ValueError("HARNESS_CURSOR_HOOKS_INVALID")
        event_order.append(event)
        for raw in entries:
            normalized = _cursor_normalize_entry(raw)
            if normalized is None or _cursor_is_managed_entry(normalized):
                continue
            preserved.setdefault(event, []).append(normalized)
    return event_order, preserved


def render_cursor_hooks(plan: LifecycleRenderPlan, *, existing_document=None) -> bytes:
    """Render Cursor-native hooks.json with a merge-preserving managed projection."""
    if plan.provider_id is not ProviderId.CURSOR or not plan.green:
        raise ValueError("cannot render refused lifecycle plan")
    event_order, preserved = _cursor_collect_preserved(existing_document)
    managed = {}
    for binding in sorted((item for item in plan.bindings if item.support_level == "hook-native"),
                          key=lambda item: (item.event, item.surface_id)):
        managed.setdefault(binding.event, []).append(_cursor_entry_from_binding(binding))
    events = list(event_order)
    for event in sorted(set(managed) - set(events)):
        events.append(event)
    hooks = {}
    for event in events:
        merged_entries = []
        merged_entries.extend(preserved.get(event, ()))
        merged_entries.extend(managed.get(event, ()))
        if merged_entries:
            hooks[event] = merged_entries
    return (json.dumps({"version": 1, "hooks": hooks}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render_cursor_hook_handler() -> bytes:
    """Generate the Cursor lifecycle dispatcher (P0-P4 Cursor surfaces)."""
    return b'''#!/usr/bin/env python3
import argparse, datetime, hashlib, importlib.util, json, os, re, shlex, subprocess, sys
from pathlib import Path

_RM_HEAD_RE = re.compile(r"\\b(rm|rmdir)\\b")
_EVENT_FIELDS = {
    "beforeShellExecution": ("command",),
    "afterShellExecution": ("command", "duration", "sandbox"),
    "preToolUse": ("tool_name", "tool_input"),
    "subagentStop": ("status", "loop_count"),
    "sessionStart": ("session_id",),
    "sessionEnd": ("reason",),
    "stop": ("status", "loop_count"),
}
_COMMON_FIELDS = ("hook_event_name", "conversation_id")
_REASON_TO_OUTCOME = {
    "completed": "ok",
    "aborted": "unknown",
    "error": "failed",
    "window_close": "unknown",
    "user_close": "unknown",
}
_GATE_MODES = ("off", "warn", "strict")
_MEMORY_MODES = ("maind", "file", "federation", "agentmemory", "off")
_CHANGELOG_SKIP_MARKER = "[changelog-skip]"
_CHANGELOG_NAME_RE = re.compile(r"changelog", re.IGNORECASE)
_CHANGELOG_SEGMENT_RE = re.compile(r"&&|\\|\\||;|\\|")
_CURSOR_FOLLOWUP_LOOP_LIMIT = 3
_PERMISSION_EMITTED = False


def _emit_permission(permission, *, user_message=None, agent_message=None):
    global _PERMISSION_EMITTED
    if _PERMISSION_EMITTED:
        return
    out = {"permission": permission}
    if user_message:
        out["user_message"] = user_message
    if agent_message:
        out["agent_message"] = agent_message
    print(json.dumps(out, ensure_ascii=False))
    _PERMISSION_EMITTED = True


def _emit_shell_allow(*, agent_message=None):
    _emit_permission("allow", agent_message=agent_message)


def _emit_shell_deny(reason):
    _emit_permission("deny", user_message=reason)


def _emit_tool_allow(*, agent_message=None):
    _emit_permission("allow", agent_message=agent_message)


def _emit_tool_deny(reason):
    _emit_permission("deny", user_message=reason)


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _conversation_id(payload):
    value = payload.get("conversation_id")
    if isinstance(value, str) and value:
        return value
    return None


def _payload_cwd(payload):
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    env_root = os.environ.get("CURSOR_PROJECT_DIR")
    if env_root:
        return env_root
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        for item in roots:
            if isinstance(item, str) and item:
                return item
    return os.getcwd()


def _carrier_value(cwd, name):
    """Value of `name` in the committed carrier .swissknifeman/hooks.env: the Cursor key, then the general one."""
    try:
        text = (Path(cwd) / ".swissknifeman" / "hooks.env").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    found = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        found[key.strip()] = value.strip()
    return found.get(name + "__CURSOR", found.get(name))


def _carrier_name(filename, key):
    return filename.split(".")[0].replace("-", "_").upper() + "_" + key


def _read_mode(cwd, filename):
    if not cwd:
        return "off"
    carried = _carrier_value(cwd, _carrier_name(filename, "MODE"))
    if carried is not None:
        carried = carried.lower()
        return carried if carried in _GATE_MODES else "off"
    env_file = Path(cwd) / ".cursor" / filename
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError:
        return "off"
    mode = "off"
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key == "MODE":
            value = value.lower()
            mode = value if value in _GATE_MODES else "off"
    return mode


def _followup_state_path(cwd, filename):
    return Path(cwd) / ".cursor" / filename


def _load_followup_state(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _save_followup_state(path, state):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _clear_followup_state(path, key):
    state = _load_followup_state(path)
    if key not in state:
        return
    state.pop(key, None)
    _save_followup_state(path, state)


def _loop_count(payload):
    value = payload.get("loop_count")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _read_memory_config(cwd):
    mode, brain = "off", "core"
    if not cwd:
        return mode, brain
    carried_mode = _carrier_value(cwd, "MEMORY_MODE")
    carried_brain = _carrier_value(cwd, "MEMORY_BRAIN")
    if carried_mode is not None:
        lowered = carried_mode.lower()
        mode = lowered if lowered in _MEMORY_MODES else "off"
    if carried_brain:
        brain = carried_brain
    if carried_mode is not None and carried_brain:
        return mode, brain
    env_file = Path(cwd) / ".cursor" / "memory.env.ini"
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError:
        return mode, brain
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key == "MODE" and carried_mode is None:
            lowered = value.lower()
            mode = lowered if lowered in _MEMORY_MODES else "off"
        elif key == "BRAIN" and value and not carried_brain:
            brain = value
    return mode, brain


def _memory(payload):
    cwd = _payload_cwd(payload)
    mode, brain = _read_memory_config(cwd)
    if mode == "off":
        return
    project_name = Path(cwd).resolve().name if cwd else "unknown"
    out = {
        "SWISSKNIFEMAN_MEMORY_PROVIDER": mode,
        "SWISSKNIFEMAN_MEMORY_BRAIN": brain,
        "SWISSKNIFEMAN_MEMORY_SCOPE": f"project:{project_name}",
    }
    print(json.dumps({"env": out}, ensure_ascii=False))


def _emit_followup_message(payload, *, cwd, state_filename, state_key, message):
    if not isinstance(message, str):
        return False
    text = message.strip()
    loop_count = _loop_count(payload)
    if not text or loop_count is None or loop_count >= _CURSOR_FOLLOWUP_LOOP_LIMIT:
        return False
    path = _followup_state_path(cwd, state_filename)
    state = _load_followup_state(path)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    previous = state.get(state_key) if isinstance(state.get(state_key), dict) else {}
    if previous.get("message_sha256") == digest:
        state[state_key] = {"message_sha256": digest, "refused": True}
        _save_followup_state(path, state)
        sys.stderr.write("continuation refused: repeated followup without progress\\n")
        return False
    state[state_key] = {"message_sha256": digest, "refused": False}
    _save_followup_state(path, state)
    print(json.dumps({"followup_message": text}))
    return True


def _iter_hook_commands(settings, event_name):
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    entries = hooks.get(event_name)
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        command = entry.get("command")
        if isinstance(command, str) and command.strip():
            yield command.strip()
        nested = entry.get("hooks")
        if not isinstance(nested, list):
            continue
        for hook in nested:
            command = hook.get("command") if isinstance(hook, dict) else None
            if isinstance(command, str) and command.strip():
                yield command.strip()


def _claude_compat_review_gate_present(cwd):
    paths = [Path.home() / ".claude" / "settings.json"]
    if cwd:
        paths.append(Path(cwd) / ".claude" / "settings.json")
        paths.append(Path(cwd) / ".claude" / "settings.local.json")
    for path in paths:
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(settings, dict):
            continue
        for command in _iter_hook_commands(settings, "SubagentStop") or ():
            if "review-gate/review-gate.sh" in command.lower():
                return True
    return False


def _find_repo_root(payload):
    candidates = []
    env_root = os.environ.get("CURSOR_PROJECT_DIR")
    if env_root:
        candidates.append(env_root)
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        candidates.extend(item for item in roots if isinstance(item, str) and item)
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        candidates.append(cwd)
    for candidate in candidates:
        d = Path(candidate).resolve()
        for _ in range(6):
            marker = d / "packages" / "harness" / "configs" / "claude-code" / "hooks" / "auto-approve" / "lib" / "safedirs.py"
            if marker.is_file():
                return str(d)
            if d.parent == d:
                break
            d = d.parent
    for name in ("swissknifeman", "skiller", "harness", "maind"):
        import shutil
        exe = shutil.which(name)
        if not exe:
            continue
        d = os.path.dirname(os.path.realpath(exe))
        for _ in range(6):
            if os.path.isfile(os.path.join(d, ".claude-plugin", "marketplace.json")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return None


def _safe_dirs(payload):
    command = payload.get("command")
    if not isinstance(command, str) or not _RM_HEAD_RE.search(command):
        return
    root = _find_repo_root(payload)
    if root is None:
        _emit_shell_deny("security.safe-dirs: refusing rm/rmdir - harness checkout unreachable")
        sys.exit(0)
    module_path = os.path.join(root, "packages", "harness", "configs", "claude-code",
                               "hooks", "auto-approve", "lib", "safedirs.py")
    try:
        spec = importlib.util.spec_from_file_location("cursor_safedirs", module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        home = os.path.expanduser("~")
        cwd = _payload_cwd(payload)
        allow = mod.load_allowlist(home)
        safe = allow is not None and mod.command_is_safe(command, cwd, allow, home)
    except Exception:
        safe = False
    if not safe:
        _emit_shell_deny(
            f"security.safe-dirs: refusing rm/rmdir - '{command}' is not covered by the safe-dirs allowlist")
        sys.exit(0)


def _daemon_safety(payload):
    command = payload.get("command")
    if not isinstance(command, str) or os.environ.get("PERPLEXITY_DAEMON_GUARD") == "off":
        return
    root = _find_repo_root(payload)
    if root is None:
        _emit_shell_deny("lifecycle.daemon-safety: refusing command - harness core unreachable")
        sys.exit(0)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_daemon_safety_core import daemon_safety_verdict
        gate = daemon_safety_verdict(command, mode="strict")
    except Exception:
        _emit_shell_deny("lifecycle.daemon-safety: refusing command - policy core failed")
        sys.exit(0)
    match = gate.match
    if gate.decision != "deny" or match is None:
        return
    reason = (
        "BLOCKED (daemon-safety): %r matched rule %s (%s). One-time bypass: "
        "PERPLEXITY_DAEMON_GUARD=off."
        % (command, match.id, match.pattern)
    )
    _emit_shell_deny(reason)
    sys.exit(0)


def _git_guardrails(payload):
    command = payload.get("command")
    if not isinstance(command, str):
        return
    cwd = _payload_cwd(payload)
    mode = _read_mode(cwd, "git-guardrails.env.ini")
    if mode == "off":
        return
    root = _find_repo_root(payload)
    if root is None:
        _emit_shell_deny("lifecycle.git-guardrails: refusing command - harness core unreachable")
        sys.exit(0)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_git_guardrails_core import git_guardrails_verdict
        gate = git_guardrails_verdict(command, mode=mode)
    except Exception:
        _emit_shell_deny("lifecycle.git-guardrails: refusing command - policy core failed")
        sys.exit(0)
    match = gate.match
    if match is None or gate.decision == "allow":
        return
    reason = ("git-guardrails: %r matched rule %s (%s)."
              % (command, match.id, match.pattern))
    if gate.decision == "deny":
        _emit_shell_deny(reason)
        sys.exit(0)
    _emit_shell_allow(agent_message="[warn] " + reason)


def _commit_messages(command):
    if not isinstance(command, str) or not command.strip():
        return []
    for segment in _CHANGELOG_SEGMENT_RE.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        for index in range(len(tokens) - 1):
            if tokens[index] == "git" and tokens[index + 1] == "commit":
                rest = tokens[index + 2:]
                return [rest[item + 1] for item in range(len(rest) - 1) if rest[item] == "-m"]
    return []


def _git_lines(cwd, *args):
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    text = out.stdout.decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line]


def _changelog_gate(payload):
    command = payload.get("command")
    if not isinstance(command, str):
        return
    cwd = _payload_cwd(payload)
    mode = _read_mode(cwd, "changelog-gate.env.ini")
    if mode == "off":
        return
    messages = _commit_messages(command)
    if not messages:
        return
    if _CHANGELOG_SKIP_MARKER in "\\n".join(messages):
        return
    root = _find_repo_root(payload)
    if root is None:
        _emit_shell_deny("lifecycle.changelog-gate: refusing command - harness core unreachable")
        sys.exit(0)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_changelog_gate_core import changelog_gate_verdict
        gate = changelog_gate_verdict(messages[0], mode=mode)
    except Exception:
        _emit_shell_deny("lifecycle.changelog-gate: refusing command - policy core failed")
        sys.exit(0)
    if gate.match is None or gate.decision == "allow":
        return
    files = _git_lines(cwd, "ls-files")
    if not files or not any(_CHANGELOG_NAME_RE.search(path) for path in files):
        return
    staged = _git_lines(cwd, "diff", "--cached", "--name-only")
    if staged and any(_CHANGELOG_NAME_RE.search(path) for path in staged):
        return
    head = messages[0].split(":", 1)[0]
    reason = ("changelog-gate: commit %r matched rule %s but [Unreleased] is untouched. "
              "Stage a CHANGELOG entry or add [changelog-skip]."
              % (head, gate.match.id))
    if gate.decision == "deny":
        _emit_shell_deny(reason)
        sys.exit(0)
    _emit_shell_allow(agent_message="[warn] " + reason)


def _managed_pack_files(cwd):
    result = {}
    try:
        lock = json.loads((Path(cwd) / ".claude" / "agent-pack.lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    packs = lock.get("packs") if isinstance(lock, dict) else None
    if not isinstance(packs, dict):
        return result
    for pack_name, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        for item in pack.get("files") or []:
            if isinstance(item, dict) and item.get("target") and not item.get("user_owned"):
                target = str(item["target"])
                result[target] = pack_name
                result[str(Path(cwd) / target)] = pack_name
    return result


def _pack_guard(payload):
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str):
        return
    mode = _read_mode(_payload_cwd(payload), "pack-guard.env.ini")
    if mode == "off":
        return
    cwd = _payload_cwd(payload)
    managed = _managed_pack_files(cwd)
    if not managed:
        return
    tool_input = payload.get("tool_input")
    try:
        haystack = json.dumps({"tool_name": tool_name, "tool_input": tool_input},
                              ensure_ascii=False)
    except (TypeError, ValueError):
        return
    root = _find_repo_root(payload)
    if root is None:
        _emit_tool_deny("lifecycle.pack-guard: refusing command - harness core unreachable")
        sys.exit(0)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_pack_guard_core import matched_target, pack_guard_verdict
        gate = pack_guard_verdict(haystack, mode=mode, managed_targets=tuple(managed))
    except Exception:
        _emit_tool_deny("lifecycle.pack-guard: refusing command - policy core failed")
        sys.exit(0)
    match = gate.match
    if match is None or gate.decision == "allow":
        return
    hit = matched_target(match.id) or "<unknown>"
    pack = managed.get(hit, "unknown")
    reason = ("pack-guard: payload matched managed target %r from pack %r."
              % (hit, pack))
    if gate.decision == "deny":
        _emit_tool_deny(reason)
        sys.exit(0)
    _emit_tool_allow(agent_message="[warn] " + reason)


def _review_gate(payload):
    cwd = _payload_cwd(payload)
    mode = _read_mode(cwd, "review-gate.env.ini")
    if mode == "off":
        return
    if payload.get("status") != "completed":
        return
    if _claude_compat_review_gate_present(cwd):
        sys.stderr.write("review-gate: skipped because Claude-compat SubagentStop hook is already registered\\n")
        return
    config_path = Path.home() / ".claude" / "hooks" / "review-gate" / "config.json"
    try:
        check = json.loads(config_path.read_text(encoding="utf-8")).get("check_command") or ""
    except (OSError, ValueError):
        check = ""
    if not check:
        return
    try:
        result = subprocess.run(["bash", "-c", check], cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=120, check=False)
    except OSError:
        return
    conversation = _conversation_id(payload)
    subagent_type = payload.get("subagent_type")
    if not isinstance(subagent_type, str):
        subagent_type = "subagent"
    state_key = f"{conversation or 'noconversation'}:{subagent_type}"
    state_path = _followup_state_path(cwd, "review-gate.state.json")
    if result.returncode == 0:
        _clear_followup_state(state_path, state_key)
        return
    if mode != "strict":
        return
    body = result.stdout.decode("utf-8", errors="replace").strip()
    evidence = body if body else "declared review check failed"
    followup = ("Review gate denied completion: fix the failing review check and rerun `%s`."
                "\\nCheck output:\\n%s" % (check, evidence))
    _emit_followup_message(payload, cwd=cwd, state_filename="review-gate.state.json",
                           state_key=state_key, message=followup)


def _plan_guard(payload):
    cwd = _payload_cwd(payload)
    mode = _read_mode(cwd, "plan-guard.env.ini")
    if mode == "off":
        return
    root = _find_repo_root(payload)
    if root is None:
        _emit_tool_deny("lifecycle.plan-guard: refusing command - harness core unreachable")
        sys.exit(0)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_plan_guard_core import MESSAGE, plan_guard_hit
        hit = plan_guard_hit(payload.get("tool_input"), cwd)
    except Exception:
        _emit_tool_deny("lifecycle.plan-guard: refusing command - policy core failed")
        sys.exit(0)
    if hit is None:
        return
    reason = "plan-guard: %s: %s" % (MESSAGE, hit)
    if mode == "strict":
        _emit_tool_deny(reason)
        sys.exit(0)
    _emit_tool_allow(agent_message="[warn] " + reason)


def _first_command_token(command):
    if not isinstance(command, str) or not command.strip():
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    index = 0
    if tokens[index] == "env":
        index += 1
        while index < len(tokens):
            token = tokens[index]
            if "=" in token and not token.startswith("-"):
                index += 1
                continue
            break
    while index < len(tokens) and tokens[index] in {"command", "builtin", "nohup", "time"}:
        index += 1
    if index >= len(tokens):
        return None
    return os.path.basename(tokens[index]) or None


def _append_jsonl(path, payload):
    line = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


_SYMBOL_TOOLS = frozenset({
    "find_symbol", "find_referencing_symbols", "get_symbols_overview",
    "find_implementations", "find_declaration", "replace_symbol_body",
    "insert_after_symbol", "insert_before_symbol", "rename_symbol",
    "safe_delete_symbol", "replace_content", "replace_in_files",
    "get_diagnostics_for_file",
})
_CODEGRAPH_SERVERS = (
    "codegraph", "serena", "plugin_core_codegraph", "plugin-core-codegraph",
    "laravel-boost", "laravel_boost",
)


def _codegraph_server_match(server):
    norm = server.lower().replace("-", "_")
    return any(marker.replace("-", "_") in norm for marker in _CODEGRAPH_SERVERS)


def _codegraph_tool(name):
    if not isinstance(name, str) or not name:
        return None
    if name in _SYMBOL_TOOLS:
        return name
    low = name.lower()
    if low in _SYMBOL_TOOLS:
        return low
    if low.startswith("mcp:"):
        parts = name.split(":", 2)
        if len(parts) >= 3 and _codegraph_server_match(parts[1]):
            return parts[2]
        return None
    if not name.startswith("mcp__"):
        return None
    tail = name.rsplit("__", 1)[-1]
    server = name[len("mcp__"):-(len(tail) + 2)]
    if _codegraph_server_match(server):
        return tail
    return None


def _tool_sidecar_path(cwd, conversation_id):
    return Path(cwd) / ".cursor" / "state" / (conversation_id + ".tools.jsonl")


def _tool_telemetry(payload):
    conversation_id = _conversation_id(payload)
    tool_name = payload.get("tool_name")
    if conversation_id is None or not isinstance(tool_name, str) or not tool_name:
        return
    cwd = _payload_cwd(payload)
    entry = {"tool": tool_name, "ts": _utc_now()}
    cg = _codegraph_tool(tool_name)
    if cg:
        entry["codegraph_op"] = cg
    try:
        path = _tool_sidecar_path(cwd, conversation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _append_jsonl(path, entry)
    except OSError:
        pass


def _aggregate_tool_sidecar(path):
    counts = {}
    codegraph = {}
    if not path.is_file():
        return counts, codegraph
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return counts, codegraph
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        tool = row.get("tool")
        if isinstance(tool, str) and tool:
            counts[tool] = counts.get(tool, 0) + 1
        op = row.get("codegraph_op")
        if isinstance(op, str) and op:
            rec = codegraph.setdefault(op, {"calls": 0})
            rec["calls"] += 1
    return counts, codegraph


def _command_log(payload):
    command = payload.get("command")
    if not isinstance(command, str) or not command:
        return
    duration = payload.get("duration")
    sandbox = payload.get("sandbox")
    conversation_id = _conversation_id(payload)
    if (conversation_id is None
            or not isinstance(duration, (int, float)) or isinstance(duration, bool)
            or not isinstance(sandbox, bool)):
        return
    command_class = _first_command_token(command) or "unknown"
    entry = {
        "schema": 1,
        "provider_id": "cursor",
        "event_kind": "shell_execution",
        "session_id": conversation_id,
        "conversation_id": conversation_id,
        "occurred_at": _utc_now(),
        "command_sha256": "sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "command_class": command_class,
        "duration": duration,
        "sandbox": sandbox,
        "outcome": "observed",
    }
    try:
        _append_jsonl(Path(_payload_cwd(payload)) / ".cursor" / "logs" / "commands.jsonl", entry)
    except OSError:
        pass


def _run_report(payload):
    reason = payload.get("reason")
    conversation_id = _conversation_id(payload)
    if reason not in _REASON_TO_OUTCOME or conversation_id is None:
        return
    cwd = _payload_cwd(payload)
    cursor = {"end_reason": reason}
    final_status = payload.get("final_status")
    if isinstance(final_status, str) and final_status:
        cursor["final_status"] = final_status
    native_session = payload.get("session_id")
    if isinstance(native_session, str) and native_session:
        cursor["native_session_id"] = native_session
    duration_ms = payload.get("duration_ms")
    if isinstance(duration_ms, (int, float)) and not isinstance(duration_ms, bool):
        cursor["duration_ms"] = duration_ms
    sidecar = _tool_sidecar_path(cwd, conversation_id)
    by_name, codegraph = _aggregate_tool_sidecar(sidecar)
    record = {
        "schema": 2,
        "provider_id": "cursor",
        "session_id": conversation_id,
        "conversation_id": conversation_id,
        "cwd": cwd,
        "occurred_at": _utc_now(),
        "event_kind": "run_summary",
        "outcome": _REASON_TO_OUTCOME[reason],
        "metrics": {},
        "cursor": cursor,
    }
    if by_name:
        record["tools"] = {"total": sum(by_name.values()), "by_name": by_name}
    if codegraph:
        record["codegraph"] = codegraph
    try:
        runs = Path(cwd) / ".cursor" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        gitignore = runs / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\\n", encoding="utf-8")
        target = runs / (conversation_id + ".json")
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\\n",
                       encoding="utf-8")
        os.replace(tmp, target)
        if sidecar.is_file():
            sidecar.unlink()
    except OSError:
        pass


_HANDLERS = {
    "security.safe-dirs": _safe_dirs,
    "lifecycle.memory": _memory,
    "lifecycle.daemon-safety": _daemon_safety,
    "lifecycle.git-guardrails": _git_guardrails,
    "lifecycle.changelog-gate": _changelog_gate,
    "lifecycle.pack-guard": _pack_guard,
    "lifecycle.plan-guard": _plan_guard,
    "lifecycle.review-gate": _review_gate,
    "lifecycle.command-log": _command_log,
    "lifecycle.tool-telemetry": _tool_telemetry,
    "lifecycle.run-report": _run_report,
}
_SURFACE_EVENTS = {
    "security.safe-dirs": "beforeShellExecution",
    "lifecycle.memory": "sessionStart",
    "lifecycle.daemon-safety": "beforeShellExecution",
    "lifecycle.git-guardrails": "beforeShellExecution",
    "lifecycle.changelog-gate": "beforeShellExecution",
    "lifecycle.pack-guard": "preToolUse",
    "lifecycle.plan-guard": "preToolUse",
    "lifecycle.tool-telemetry": "preToolUse",
    "lifecycle.review-gate": "subagentStop",
    "lifecycle.command-log": "afterShellExecution",
    "lifecycle.run-report": "sessionEnd",
}

parser = argparse.ArgumentParser()
parser.add_argument("--surface", required=True)
args = parser.parse_args()
if args.surface not in _SURFACE_EVENTS:
    sys.exit(2)
try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError):
    event = _SURFACE_EVENTS[args.surface]
    if event == "beforeShellExecution":
        _emit_shell_allow()
        sys.exit(0)
    if event == "preToolUse":
        _emit_tool_allow()
        sys.exit(0)
    sys.stderr.write(f"lifecycle: invalid JSON stdin for {args.surface}\\n")
    sys.exit(2)
if not isinstance(payload, dict):
    event = _SURFACE_EVENTS[args.surface]
    if event == "beforeShellExecution":
        _emit_shell_allow()
        sys.exit(0)
    if event == "preToolUse":
        _emit_tool_allow()
        sys.exit(0)
    sys.stderr.write(f"lifecycle: non-object payload for {args.surface}\\n")
    sys.exit(2)
event = _SURFACE_EVENTS[args.surface]
required = set(_COMMON_FIELDS)
required.update(_EVENT_FIELDS.get(event, ()))
optional = {"conversation_id"}
missing = required - set(payload.keys()) - optional
if missing or payload.get("hook_event_name") != event:
    if event == "beforeShellExecution":
        _emit_shell_allow()
        sys.exit(0)
    if event == "preToolUse":
        _emit_tool_allow()
        sys.exit(0)
    sys.stderr.write(
        f"lifecycle: invalid payload for {args.surface}: "
        f"missing={{sorted(missing)}} event={{payload.get('hook_event_name')!r}}\\n"
    )
    sys.exit(2)
_HANDLERS[args.surface](payload)
if event == "beforeShellExecution":
    _emit_shell_allow()
elif event == "preToolUse":
    _emit_tool_allow()
'''


def plan_cursor_lifecycle_artifacts(plan: LifecycleRenderPlan, *, bindings_path: Path,
                                    existing_document=None):
    """P2 artifact seam for Cursor hooks registration and handler."""
    if plan.provider_id is not ProviderId.CURSOR or not plan.green:
        raise ValueError("cannot plan refused lifecycle artifact")
    source = ArtifactSource("harness.cursor.lifecycle-bindings",
                            "packages/harness/configs/cursor/hooks/lifecycle-context-bindings.json",
                            sha256_digest(Path(bindings_path).read_bytes()))
    identity = ArtifactAdapterIdentity("harness.cursor.lifecycle", _CODEX_HOOK_ADAPTER_VERSION,
                                       ProviderId.CURSOR, "1.0.0", ())
    hooks = plan_artifact_render(ArtifactRenderRequest("harness.cursor.lifecycle.hooks", (source,),
        ArtifactTarget(".cursor/hooks.json", ("whole-file", ())), identity, (), {},
        lambda _request: render_cursor_hooks(plan, existing_document=existing_document)))
    handler = plan_artifact_render(ArtifactRenderRequest("harness.cursor.lifecycle.handler", (source,),
        ArtifactTarget(".cursor/hooks/lifecycle.py", ("whole-file", ())), identity, (), {},
        lambda _request: render_cursor_hook_handler()))
    return hooks, handler


_CODEX_ROUTER_CATALOG_PATH = ("packages/harness/configs/claude-code/hooks/"
                              "agent-router/config.json")  # hub-relative identifier recorded in locks
_CODEX_ROUTER_CATALOG_FILE = (Path(__file__).resolve().parents[2]
                              / "configs/claude-code/hooks/agent-router/config.json")


def _codex_router_catalog():
    """Read the same catalog `~/.claude/hooks/agent-router/config.json` uses and project
    its command names into Codex's own bare invocation form (`planner:x`, not `/planner:x`)."""
    catalog = json.loads(_CODEX_ROUTER_CATALOG_FILE.read_text(encoding="utf-8"))
    commands = [{"name": entry["name"].replace("/planner:", "planner:", 1),
                "weight": entry.get("weight", 1), "keywords": entry["keywords"]}
               for entry in catalog.get("commands", [])]
    hint_template = catalog.get(
        "hint_template", "[intent-router] bias (non-authoritative): top={name} score={score}{runners}")
    return commands, hint_template


def render_codex_hook_handler(*, state_dir: str = ".codex") -> bytes:
    """Generate the multi-surface dispatcher: one generator, one per-surface handler table.

    Codex and Grok share this dispatcher, but their payload spellings differ.  The generated
    adapter normalizes both shapes before dispatch.  A malformed or unknown Grok payload is
    deliberately fail-open: a lifecycle observer must never brick a session.  Codex keeps its
    fail-closed contract; explicit policy refusals are the only other exit-2 path.
    """
    if state_dir not in {".codex", ".grok"}:
        raise ValueError("HARNESS_MAPPING_MISSING")
    provider_id = "grok" if state_dir == ".grok" else "codex"
    router_commands, hint_template = _codex_router_catalog()
    router_catalog_literal = json.dumps(router_commands, ensure_ascii=False)
    return f'''#!/usr/bin/env python3
import argparse, datetime, importlib.util, json, os, re, shlex, shutil, subprocess, sys
from pathlib import Path

_STATE_DIR = {state_dir!r}
_PROVIDER_ID = {provider_id!r}
_SURFACE_EVENTS = {{
    "context.observer": "SessionStart",
    "lifecycle.command-log": "PreToolUse",
    "lifecycle.tool-telemetry": "PreToolUse",
    "lifecycle.run-report": "SessionEnd",
    "lifecycle.router": "UserPromptSubmit",
    "lifecycle.memory": "SessionStart",
    "lifecycle.pack-guard": "PreToolUse",
    "lifecycle.plan-guard": "PreToolUse",
    "lifecycle.changelog-gate": "PreToolUse",
    "lifecycle.review-gate": "SubagentStop",
    "security.safe-dirs": "PreToolUse",
    "lifecycle.daemon-safety": "PreToolUse",
    "lifecycle.git-guardrails": "PreToolUse",
}}
_EVENT_FIELDS = {{
    "SessionStart": ("source",),
    "PreToolUse": ("tool_name", "tool_input"),
    "SessionEnd": ("reason",),
    "UserPromptSubmit": ("prompt",),
    "SubagentStop": ("agent_type",),
    "Stop": ("stop_hook_active", "last_assistant_message"),
}}
_GATE_MODES = ("off", "warn", "strict")


def _adapter_log(message):
    try:
        sys.stderr.write("[harness lifecycle] " + str(message) + "\\n")
    except Exception:
        pass


def _canonical_event(value):
    if not isinstance(value, str):
        return ""
    compact = value.replace("_", "").replace("-", "").lower()
    return {{
        "pretooluse": "PreToolUse",
        "sessionstart": "SessionStart",
        "sessionend": "SessionEnd",
        "userpromptsubmit": "UserPromptSubmit",
        "subagentstop": "SubagentStop",
        "stop": "Stop",
    }}.get(compact, value)


def _normalize_payload(raw, expected_event):
    """Accept Claude snake_case and Grok camelCase hook envelopes.

    Grok supplies ``hookEventName``, ``toolName``, ``toolInput`` and ``sessionId``;
    Claude-shaped providers use their snake_case counterparts.  Missing optional
    fields are normalized to benign defaults.  An incompatible envelope returns
    ``None`` so the caller can log and fail open (Grok) or exit 2 (Codex).
    """
    if not isinstance(raw, dict):
        return None
    payload = dict(raw)
    event = _canonical_event(raw.get("hook_event_name") or raw.get("hookEventName"))
    if event != expected_event:
        return None
    payload["hook_event_name"] = event
    payload["tool_name"] = raw.get("tool_name") or raw.get("toolName")
    tool_input = raw.get("tool_input")
    if tool_input is None:
        tool_input = raw.get("toolInput")
    if expected_event == "PreToolUse" and not isinstance(tool_input, dict):
        return None
    payload["tool_input"] = tool_input if isinstance(tool_input, dict) else {{}}
    payload["session_id"] = (raw.get("session_id") or raw.get("sessionId")
                             or os.environ.get("GROK_SESSION_ID", ""))
    payload["cwd"] = (raw.get("cwd") or raw.get("workspaceRoot")
                      or os.environ.get("GROK_WORKSPACE_ROOT", "") or os.getcwd())
    payload["permission_mode"] = raw.get("permission_mode") or raw.get("permissionMode") or ""
    payload["model"] = raw.get("model") or ""
    return payload


def _carrier_value(cwd, name):
    """Value of `name` in the committed carrier .swissknifeman/hooks.env: the provider key, then the general one."""
    try:
        text = (Path(cwd) / ".swissknifeman" / "hooks.env").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    found = {{}}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        found[key.strip()] = value.strip()
    return found.get(name + "__" + _PROVIDER_ID.upper(), found.get(name))


def _read_mode(cwd, filename):
    """MODE from the carrier .swissknifeman/hooks.env, then from <cwd>/<_STATE_DIR>/<filename>.
    Missing/unreadable/unknown value -> off (safe default, matches the Claude-side
    gates and the phase's explicit "inactive by default" requirement)."""
    if not cwd:
        return "off"
    carried = _carrier_value(cwd, filename.split(".")[0].replace("-", "_").upper() + "_MODE")
    if carried is not None:
        carried = carried.lower()
        return carried if carried in _GATE_MODES else "off"
    f = Path(cwd) / _STATE_DIR / filename
    try:
        text = f.read_text(encoding="utf-8")
    except OSError:
        return "off"
    mode = "off"
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key == "MODE":
            value = value.lower()
            mode = value if value in _GATE_MODES else "off"
    return mode
_ROUTER_CATALOG = {router_catalog_literal}
_ROUTER_HINT_TEMPLATE = {hint_template!r}
_ROUTER_THRESHOLD = 2


def _observer(payload):
    print(json.dumps({{"systemMessage": "[harness observer] read-only policy active"}}))


_SYMBOL_TOOLS = frozenset({{
    "find_symbol", "find_referencing_symbols", "get_symbols_overview",
    "find_implementations", "find_declaration", "replace_symbol_body",
    "insert_after_symbol", "insert_before_symbol", "rename_symbol",
    "safe_delete_symbol", "replace_content", "replace_in_files",
    "get_diagnostics_for_file",
}})
_CODEGRAPH_SERVERS = (
    "codegraph", "serena", "plugin_core_codegraph", "plugin-core-codegraph",
    "laravel-boost", "laravel_boost",
)


def _codegraph_server_match(server):
    norm = server.lower().replace("-", "_")
    return any(marker.replace("-", "_") in norm for marker in _CODEGRAPH_SERVERS)


def _codegraph_tool(name):
    if not isinstance(name, str) or not name:
        return None
    if name in _SYMBOL_TOOLS:
        return name
    low = name.lower()
    if low in _SYMBOL_TOOLS:
        return low
    if low.startswith("mcp:"):
        parts = name.split(":", 2)
        if len(parts) >= 3 and _codegraph_server_match(parts[1]):
            return parts[2]
        return None
    if not name.startswith("mcp__"):
        return None
    tail = name.rsplit("__", 1)[-1]
    server = name[len("mcp__"):-(len(tail) + 2)]
    if _codegraph_server_match(server):
        return tail
    return None


def _append_jsonl(path, payload):
    line = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def _tool_sidecar_path(cwd, session_id):
    return Path(cwd) / _STATE_DIR / "state" / (str(session_id) + ".tools.jsonl")


def _aggregate_tool_sidecar(path):
    counts = {{}}
    codegraph = {{}}
    if not path.is_file():
        return counts, codegraph
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return counts, codegraph
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        tool = row.get("tool")
        if isinstance(tool, str) and tool:
            counts[tool] = counts.get(tool, 0) + 1
        op = row.get("codegraph_op")
        if isinstance(op, str) and op:
            rec = codegraph.setdefault(op, {{"calls": 0}})
            rec["calls"] += 1
    return counts, codegraph


def _run_report_lib_path(cwd):
    candidates = []
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2, check=False)
        root = proc.stdout.strip() if proc.returncode == 0 else ""
        if root:
            candidates.append(Path(root) / "packages/harness/configs/claude-code/hooks/run-report/_lib.py")
    except (OSError, subprocess.SubprocessError):
        pass
    candidates.append(Path.home() / ".claude/hooks/run-report/_lib.py")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _parse_transcript_report(cwd, tpath):
    lib = _run_report_lib_path(cwd)
    if lib is None:
        return None
    try:
        spec = importlib.util.spec_from_file_location("run_report_lib", lib)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with open(tpath, encoding="utf-8", errors="replace") as handle:
            return mod.parse_events(handle, transcript_path=tpath, cwd=cwd)
    except Exception:
        return None


def _tool_telemetry(payload):
    session_id = payload.get("session_id")
    tool_name = payload.get("tool_name")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd or not isinstance(session_id, str) or not session_id:
        return
    if not isinstance(tool_name, str) or not tool_name:
        return
    entry = {{"tool": tool_name, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()}}
    cg = _codegraph_tool(tool_name)
    if cg:
        entry["codegraph_op"] = cg
    try:
        _append_jsonl(_tool_sidecar_path(cwd, session_id), entry)
    except OSError:
        pass


def _command_log(payload):
    log_dir = Path.home() / _STATE_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        tool_input = payload.get("tool_input") or {{}}
        entry = {{"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "cwd": payload.get("cwd", ""), "session": payload.get("session_id", ""),
                 "command": tool_input.get("command"), "description": tool_input.get("description")}}
        with (log_dir / "bash-commands.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\\n")
    except OSError:
        pass


def _run_report(payload):
    cwd = payload.get("cwd")
    if not cwd:
        return
    sid = payload.get("session_id") or "session"
    sid = "".join(c for c in str(sid) if c.isalnum() or c in "-_") or "session"
    tpath = payload.get("transcript_path")
    record = None
    if isinstance(tpath, str) and tpath:
        tpath = os.path.expanduser(tpath)
        if os.path.isfile(tpath):
            record = _parse_transcript_report(cwd, tpath)
    sidecar = _tool_sidecar_path(cwd, sid)
    by_name, codegraph = _aggregate_tool_sidecar(sidecar)
    if record is None:
        record = {{"schema": 1, "session_id": sid, "cwd": cwd,
                   "reason": payload.get("reason", ""),
                   "transcript_path": tpath if isinstance(tpath, str) else None}}
    else:
        record["schema"] = 2
        record["provider_id"] = _PROVIDER_ID
        record["session_id"] = sid
        record["cwd"] = cwd
        record["reason"] = payload.get("reason") or ""
        if isinstance(tpath, str):
            record["transcript_path"] = tpath
        try:
            record["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        except Exception:
            pass
    if by_name:
        record["tools"] = {{"total": sum(by_name.values()), "by_name": by_name}}
    if codegraph:
        existing = record.get("codegraph") if isinstance(record.get("codegraph"), dict) else {{}}
        for op, rec in codegraph.items():
            cur = existing.setdefault(op, {{"calls": 0}})
            cur["calls"] += rec.get("calls", 0)
        record["codegraph"] = existing
    runs_dir = Path(cwd) / _STATE_DIR / "runs"
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        gitignore = runs_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\\n", encoding="utf-8")
        target = runs_dir / (sid + ".json")
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\\n",
                       encoding="utf-8")
        os.replace(tmp, target)
        if sidecar.is_file():
            sidecar.unlink()
    except OSError:
        pass


def _router(payload):
    text = payload.get("prompt") or ""
    if not isinstance(text, str) or not text.strip():
        return
    low = text.lower()
    scored = []
    for entry in _ROUTER_CATALOG:
        score = sum(entry.get("weight", 1) for keyword in entry["keywords"] if keyword in low)
        if score > 0:
            scored.append((entry["name"], score))
    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored or scored[0][1] < _ROUTER_THRESHOLD:
        return
    top_name, top_score = scored[0]
    runners = ", ".join(f"{{name}} ({{score}})" for name, score in scored[1:3])
    try:
        hint = _ROUTER_HINT_TEMPLATE.format(
            name=top_name, score=top_score,
            runners=("; runners-up: " + runners) if runners else "")
    except (KeyError, IndexError):
        return
    print(json.dumps({{"systemMessage": hint}}))


def _memory(payload):
    cwd = payload.get("cwd")
    mode, brain = "maind", "core"
    if cwd:
        carried_mode = _carrier_value(cwd, "MEMORY_MODE")
        carried_brain = _carrier_value(cwd, "MEMORY_BRAIN")
        if carried_mode is not None:
            mode = carried_mode
        if carried_brain:
            brain = carried_brain
        ini = Path(cwd) / _STATE_DIR / "memory.env.ini"
        try:
            for line in ini.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                if key == "MODE" and carried_mode is None:
                    mode = value
                elif key == "BRAIN" and not carried_brain:
                    brain = value
        except OSError:
            pass
    if mode != "maind":
        return
    try:
        import subprocess
        result = subprocess.run(["maind", "memory", "status", "--brain", brain],
                                capture_output=True, text=True, timeout=5, check=False)
        if result.returncode == 0 and result.stdout.strip():
            print(json.dumps({{"systemMessage": "[harness memory] " + result.stdout.strip()}}))
    except Exception:
        pass


def _managed_pack_files(cwd):
    """target (project-relative) -> pack name, from .claude/agent-pack.lock.json — the
    SAME lock a Codex session sees when it edits a Claude-onboarded project's managed
    assets (codex-parity-verdicts-v1.md §3.5). Without user_owned entries."""
    result = {{}}
    try:
        lock = json.loads((Path(cwd) / ".claude" / "agent-pack.lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    packs = lock.get("packs") if isinstance(lock, dict) else None
    if not isinstance(packs, dict):
        return result
    for pack_name, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        for f in pack.get("files") or []:
            if isinstance(f, dict) and f.get("target") and not f.get("user_owned"):
                result[f["target"]] = pack_name
    return result


def _pack_guard(payload):
    cwd = payload.get("cwd")
    mode = _read_mode(cwd, "pack-guard.env.ini")
    if mode == "off" or not cwd:
        return
    managed = _managed_pack_files(cwd)
    if not managed:
        return
    tool_input = payload.get("tool_input") or {{}}
    try:
        haystack = json.dumps(tool_input, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    root = _find_repo_root()
    if root is None:
        sys.stderr.write("lifecycle.pack-guard: refusing command — harness core unreachable\\n")
        sys.exit(2)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_pack_guard_core import matched_target, pack_guard_verdict
        gate = pack_guard_verdict(haystack, mode=mode, managed_targets=tuple(managed))
    except Exception:
        sys.stderr.write("lifecycle.pack-guard: refusing command — policy core failed\\n")
        sys.exit(2)
    match = gate.match
    if match is None or gate.decision == "allow":
        return
    hit = matched_target(match.id) or "<unknown>"
    pack = managed.get(hit, "unknown")
    msg = (f"pack-guard: command payload matched managed target '{{hit}}' from pack '{{pack}}' "
          f"(swissknifeman:generated) — edit the pack overlay or accept the change "
          f"through 'harness agent-packs upgrade': {{hit}}")
    if gate.decision == "deny":
        sys.stderr.write(msg + "\\n")
        sys.exit(2)
    print(json.dumps({{"systemMessage": "[warn] " + msg}}))


_CHANGELOG_NAME_RE = re.compile(r"changelog", re.IGNORECASE)
_CHANGELOG_SEGMENT_RE = re.compile(r"&&|\\|\\||;|\\|")


def _commit_messages(command):
    if not isinstance(command, str) or not command.strip():
        return []
    for segment in _CHANGELOG_SEGMENT_RE.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        for i in range(len(tokens) - 1):
            if tokens[i] == "git" and tokens[i + 1] == "commit":
                rest = tokens[i + 2:]
                return [rest[j + 1] for j in range(len(rest) - 1) if rest[j] == "-m"]
    return []


def _git_lines(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", cwd, *args], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=10, check=False)
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return [line for line in out.stdout.decode("utf-8", errors="replace").splitlines() if line]


def _changelog_gate(payload):
    if payload.get("tool_name") != "Bash":
        return
    cwd = payload.get("cwd")
    mode = _read_mode(cwd, "changelog-gate.env.ini")
    if mode == "off" or not cwd:
        return
    tool_input = payload.get("tool_input") or {{}}
    messages = _commit_messages(tool_input.get("command"))
    if not messages:
        return
    if "[changelog-skip]" in "\\n".join(messages):
        return
    root = _find_repo_root()
    if root is None:
        sys.stderr.write("lifecycle.changelog-gate: refusing command — harness core unreachable\\n")
        sys.exit(2)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_changelog_gate_core import changelog_gate_verdict
        gate = changelog_gate_verdict(messages[0], mode=mode)
    except Exception:
        sys.stderr.write("lifecycle.changelog-gate: refusing command — policy core failed\\n")
        sys.exit(2)
    if gate.match is None or gate.decision == "allow":
        return
    files = _git_lines(cwd, "ls-files")
    if not files or not any(_CHANGELOG_NAME_RE.search(f) for f in files):
        return
    staged = _git_lines(cwd, "diff", "--cached", "--name-only")
    if staged and any(_CHANGELOG_NAME_RE.search(f) for f in staged):
        return
    head = messages[0].split(":", 1)[0]
    reason = ("changelog-gate: commit %r matched rule %s but [Unreleased] is untouched. "
              "Stage a CHANGELOG entry or add [changelog-skip]."
              % (head, gate.match.id))
    if gate.decision == "deny":
        sys.stderr.write(reason + "\\n")
        sys.exit(2)
    print(json.dumps({{"systemMessage": "[warn] " + reason}}))


_REVIEW_GATE_MAX_ATTEMPTS = 3


def _review_gate(payload):
    cwd = payload.get("cwd")
    mode = _read_mode(cwd, "review-gate.env.ini")
    if mode == "off" or not cwd:
        return
    config_path = Path.home() / ".claude" / "hooks" / "review-gate" / "config.json"
    try:
        check = json.loads(config_path.read_text(encoding="utf-8")).get("check_command") or ""
    except (OSError, ValueError):
        check = ""
    if not check:
        return
    key = (payload.get("session_id") or "nosession") + ":" + (payload.get("agent_id") or "noagent")
    state_path = Path(cwd) / _STATE_DIR / "review-gate.state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {{}}
    attempts = int(state.get(key, 0)) if isinstance(state, dict) else 0
    try:
        result = subprocess.run(["bash", "-c", check], cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=120)
    except OSError:
        return
    if result.returncode == 0:
        if isinstance(state, dict) and key in state:
            del state[key]
            try:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(state), encoding="utf-8")
            except OSError:
                pass
        return
    body = result.stdout.decode("utf-8", errors="replace")
    reason = f"review-gate: check failed after subagent stop (mode={{mode}}).\\n{{body}}"
    if mode == "strict" and attempts < _REVIEW_GATE_MAX_ATTEMPTS:
        if not isinstance(state, dict):
            state = {{}}
        state[key] = attempts + 1
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state), encoding="utf-8")
        except OSError:
            pass
        sys.stderr.write(reason + "\\n")
        sys.exit(2)   # forces the subagent to continue — does not cancel it (D88)
    print(json.dumps({{"systemMessage": reason}}))


_RM_HEAD_RE = re.compile(r"\\b(rm|rmdir)\\b")


def _find_repo_root():
    for name in ("swissknifeman", "skiller", "harness", "maind"):
        exe = shutil.which(name)
        if not exe:
            continue
        d = os.path.dirname(os.path.realpath(exe))
        for _ in range(6):
            if os.path.isfile(os.path.join(d, ".claude-plugin", "marketplace.json")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return None


def _safe_dirs(payload):
    """PreToolUse deny for rm/rmdir — CALLS the single allowlist verdict core
    (packages/harness/configs/claude-code/hooks/auto-approve/lib/safedirs.py) rather
    than copying its rules (codex-parity-verdicts-v1.md §3.8). Unreachable checkout is
    a refusal, not a pass."""
    if payload.get("tool_name") != "Bash":
        return
    tool_input = payload.get("tool_input") or {{}}
    command = tool_input.get("command")
    if not isinstance(command, str) or not _RM_HEAD_RE.search(command):
        return
    root = _find_repo_root()
    if root is None:
        sys.stderr.write("security.safe-dirs: refusing rm/rmdir — harness checkout "
                         "unreachable from this session\\n")
        sys.exit(2)
    module_path = os.path.join(root, "packages", "harness", "configs", "claude-code",
                               "hooks", "auto-approve", "lib", "safedirs.py")
    try:
        spec = importlib.util.spec_from_file_location("codex_safedirs", module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        home = os.path.expanduser("~")
        cwd = payload.get("cwd") or os.getcwd()
        allow = mod.load_allowlist(home)
        safe = allow is not None and mod.command_is_safe(command, cwd, allow, home)
    except Exception:
        safe = False
    if not safe:
        sys.stderr.write(f"security.safe-dirs: refusing rm/rmdir — '{{command}}' is not "
                         f"covered by the safe-dirs allowlist\\n")
        sys.exit(2)


def _daemon_safety(payload):
    if payload.get("tool_name") != "Bash" or os.environ.get("PERPLEXITY_DAEMON_GUARD") == "off":
        return
    tool_input = payload.get("tool_input") or {{}}
    command = tool_input.get("command")
    if not isinstance(command, str):
        return
    root = _find_repo_root()
    if root is None:
        sys.stderr.write("lifecycle.daemon-safety: refusing command — harness core unreachable\\n")
        sys.exit(2)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_daemon_safety_core import daemon_safety_verdict
        gate = daemon_safety_verdict(command, mode="strict")
    except Exception:
        sys.stderr.write("lifecycle.daemon-safety: refusing command — policy core failed\\n")
        sys.exit(2)
    match = gate.match
    if gate.decision != "deny" or match is None:
        return
    sys.stderr.write(
        "BLOCKED (daemon-safety): %r matched rule %s (%s). One-time bypass: "
        "PERPLEXITY_DAEMON_GUARD=off.\\n"
        % (command, match.id, match.pattern)
    )
    sys.exit(2)


def _git_guardrails(payload):
    if payload.get("tool_name") != "Bash":
        return
    cwd = payload.get("cwd")
    mode = _read_mode(cwd, "git-guardrails.env.ini")
    if mode == "off" or not cwd:
        return
    tool_input = payload.get("tool_input") or {{}}
    command = tool_input.get("command")
    if not isinstance(command, str):
        return
    root = _find_repo_root()
    if root is None:
        sys.stderr.write("lifecycle.git-guardrails: refusing command — harness core unreachable\\n")
        sys.exit(2)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_git_guardrails_core import git_guardrails_verdict
        gate = git_guardrails_verdict(command, mode=mode)
    except Exception:
        sys.stderr.write("lifecycle.git-guardrails: refusing command — policy core failed\\n")
        sys.exit(2)
    match = gate.match
    if match is None or gate.decision == "allow":
        return
    reason = "git-guardrails: %r matched rule %s (%s)." % (command, match.id, match.pattern)
    if gate.decision == "deny":
        sys.stderr.write(reason + "\\n")
        sys.exit(2)
    print(json.dumps({{"systemMessage": "[warn] " + reason}}))


def _plan_guard(payload):
    cwd = payload.get("cwd")
    mode = _read_mode(cwd, "plan-guard.env.ini")
    if mode == "off" or not cwd:
        return
    root = _find_repo_root()
    if root is None:
        sys.stderr.write("lifecycle.plan-guard: refusing command — harness core unreachable\\n")
        sys.exit(2)
    lib_root = os.path.join(root, "packages", "harness", "lib")
    try:
        if lib_root not in sys.path:
            sys.path.insert(0, lib_root)
        from harness.lifecycle_plan_guard_core import MESSAGE, plan_guard_hit
        hit = plan_guard_hit(payload.get("tool_input"), cwd)
    except Exception:
        sys.stderr.write("lifecycle.plan-guard: refusing command — policy core failed\\n")
        sys.exit(2)
    if hit is None:
        return
    msg = "plan-guard: " + MESSAGE + ": " + hit
    if mode == "strict":
        sys.stderr.write(msg + "\\n")
        sys.exit(2)
    print(json.dumps({{"systemMessage": "[warn] " + msg}}))


_HANDLERS = {{
    "context.observer": _observer,
    "lifecycle.command-log": _command_log,
    "lifecycle.tool-telemetry": _tool_telemetry,
    "lifecycle.run-report": _run_report,
    "lifecycle.router": _router,
    "lifecycle.memory": _memory,
    "lifecycle.pack-guard": _pack_guard,
    "lifecycle.plan-guard": _plan_guard,
    "lifecycle.changelog-gate": _changelog_gate,
    "lifecycle.review-gate": _review_gate,
    "security.safe-dirs": _safe_dirs,
    "lifecycle.daemon-safety": _daemon_safety,
    "lifecycle.git-guardrails": _git_guardrails,
}}

parser = argparse.ArgumentParser()
parser.add_argument("--surface", required=True)
args = parser.parse_args()
if args.surface not in _SURFACE_EVENTS:
    if _PROVIDER_ID == "grok":
        _adapter_log("unknown lifecycle surface; allowing without dispatch")
        sys.exit(0)
    sys.exit(2)
try:
    raw_payload = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError, ValueError):
    if _PROVIDER_ID == "grok":
        _adapter_log("payload was not parseable; allowing without dispatch")
        sys.exit(0)
    sys.exit(2)
event = _SURFACE_EVENTS[args.surface]
payload = _normalize_payload(raw_payload, event)
if payload is None:
    if _PROVIDER_ID == "grok":
        _adapter_log("payload did not match the lifecycle event; allowing without dispatch")
        sys.exit(0)
    sys.exit(2)
if _PROVIDER_ID != "grok":
    required = {{"session_id", "cwd", "hook_event_name", "model"}}
    if event == "SessionStart":
        required.add("permission_mode")
    required.update(_EVENT_FIELDS.get(event, ()))
    if not required.issubset(payload):
        sys.exit(2)
try:
    _HANDLERS[args.surface](payload)
except SystemExit:
    raise
except Exception as error:
    _adapter_log("lifecycle handler failed; allowing this tool call: " + type(error).__name__)
'''.encode("utf-8")


def codex_d104_observer_fragment(plan: LifecycleRenderPlan) -> CodexLifecycleFragment:
    """Return only P5's native observer registration and companion handler bytes.

    P6 owns selection and preservation of the pre-existing memory command. This helper
    deliberately has no input for a memory command and does not merge an existing document.
    """
    if plan.provider_id is not ProviderId.CODEX or not plan.green:
        raise ValueError("cannot render refused lifecycle plan")
    bindings = [binding for binding in plan.bindings
                if binding.surface_id == "context.observer"]
    if len(bindings) != 1 or bindings[0].support_level != "hook-native":
        raise ValueError("HARNESS_MAPPING_MISSING")
    binding = bindings[0]
    if binding.event != "SessionStart":
        raise ValueError("HARNESS_MAPPING_MISSING")
    group = {"hooks": [{"type": "command", "command":
             f'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/lifecycle.py" --surface {binding.surface_id}'}]}
    if binding.matcher:
        group["matcher"] = binding.matcher
    return CodexLifecycleFragment(_D104_CODEX_HOOKS_TARGET, binding.event, group,
                                  render_codex_hook_handler())


def validate_d104_codex_lifecycle_composition(document: bytes, *, memory_command: str,
                                               fragment: CodexLifecycleFragment) -> None:
    """Fail closed on a P6-composed D104 document before P2 transfer planning.

    This is intentionally a validator, not a generic merger: P6 remains the caller that
    composes and owns its memory registration, while P5 proves its observer input is intact.
    """
    if (not isinstance(document, bytes) or not isinstance(memory_command, str)
            or not memory_command or not isinstance(fragment, CodexLifecycleFragment)
            or fragment.target_path != _D104_CODEX_HOOKS_TARGET
            or fragment.event != "SessionStart"):
        raise ValueError("HARNESS_D104_LIFECYCLE_INVALID")
    try:
        value = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("HARNESS_D104_LIFECYCLE_INVALID") from None
    if not isinstance(value, dict) or set(value) != {"hooks"}:
        raise ValueError("HARNESS_D104_LIFECYCLE_INVALID")
    hooks = value["hooks"]
    if not isinstance(hooks, dict) or "SessionStart" not in hooks:
        raise ValueError("HARNESS_D104_LIFECYCLE_INVALID")
    groups = hooks["SessionStart"]
    if not isinstance(groups, list) or len(groups) != 2:
        raise ValueError("HARNESS_D104_LIFECYCLE_INVALID")
    commands = []
    for group in groups:
        if (not isinstance(group, dict) or set(group) - {"hooks", "matcher"}
                or not isinstance(group.get("hooks"), list) or len(group["hooks"]) != 1
                or not isinstance(group["hooks"][0], dict)
                or set(group["hooks"][0]) != {"type", "command"}
                or group["hooks"][0]["type"] != "command"
                or not isinstance(group["hooks"][0]["command"], str)
                or not group["hooks"][0]["command"]
                or "matcher" in group and not isinstance(group["matcher"], str)):
            raise ValueError("HARNESS_D104_LIFECYCLE_INVALID")
        commands.append(group["hooks"][0]["command"])
    observer_command = fragment.group["hooks"][0]["command"]
    if (memory_command == observer_command or commands.count(memory_command) != 1
            or commands.count(observer_command) != 1 or len(set(commands)) != 2):
        raise ValueError("HARNESS_D104_LIFECYCLE_INVALID")


CODEX_LIFECYCLE_SCHEMA = "urn:swissknifeman:harness:codex-lifecycle:v1"
_D104_FRAGMENT_SOURCE_ID = "harness.d104.observer-fragment"
_D104_FRAGMENT_SOURCE_PATH = "packages/harness/lib/harness/hooks.py"


def d104_observer_fragment(configs: Path) -> CodexLifecycleFragment:
    """The native Codex observer registration and handler, planned from the package configs."""
    configs = Path(configs)
    lifecycle = plan_lifecycle(
        load_catalog(configs / "common" / "profile-catalog.json"),
        provider_id=ProviderId.CODEX,
        requests=(LifecycleRequest("context.observer", True),), trusted=True,
        codex_bindings_path=configs / "codex/hooks/lifecycle-context-bindings.json")
    return codex_d104_observer_fragment(lifecycle)


def codex_lifecycle_fragment_document(configs: Path) -> dict:
    """The JSON form of the observer fragment (contract `codex-lifecycle/v1`)."""
    fragment = d104_observer_fragment(configs)
    return {
        "$schema": CODEX_LIFECYCLE_SCHEMA,
        "fragment": {
            "target_path": fragment.target_path, "event": fragment.event,
            "group": fragment.group, "handler": fragment.handler_bytes.decode("utf-8"),
            "handler_sha256": sha256_digest(fragment.handler_bytes),
            "source": {
                "id": _D104_FRAGMENT_SOURCE_ID, "path": _D104_FRAGMENT_SOURCE_PATH,
                "sha256": sha256_digest(canonical_json_bytes({
                    "event": fragment.event, "group": fragment.group,
                    "handler_sha256": sha256_digest(fragment.handler_bytes)})),
            },
        },
    }


def codex_lifecycle_validation_document(configs: Path, document: bytes, memory_command: str) -> dict:
    """Validate a composed hooks document against the observer fragment; a refusal is data."""
    fragment = d104_observer_fragment(configs)
    try:
        validate_d104_codex_lifecycle_composition(document, memory_command=memory_command,
                                                  fragment=fragment)
    except ValueError as error:
        return {"$schema": CODEX_LIFECYCLE_SCHEMA, "ok": False, "code": str(error)}
    return {"$schema": CODEX_LIFECYCLE_SCHEMA, "ok": True, "code": None}


def cmd_codex_lifecycle(env, argv):
    """`harness hooks codex-lifecycle fragment|validate --json` — D104 composition inputs."""
    usage = ("harness hooks codex-lifecycle fragment --json\n"
             "harness hooks codex-lifecycle validate --document FILE --memory-command CMD --json")
    if not argv or argv[0] in ("-h", "--help"):
        print(usage)
        return
    verb, rest = argv[0], argv[1:]
    configs = Path(env.root) / "configs"
    if verb == "fragment":
        opts = parse_flags(rest, {"--json": "bool"})
        if not opts["json"]:
            die(usage)
        try:
            print(json.dumps(codex_lifecycle_fragment_document(configs), ensure_ascii=False))
        except ValueError as error:
            die(str(error))
        return
    if verb == "validate":
        opts = parse_flags(rest, {"--document": "str", "--memory-command": "str", "--json": "bool"})
        if not (opts["document"] and opts["memory_command"] and opts["json"]):
            die(usage)
        try:
            document = Path(opts["document"]).expanduser().read_bytes()
        except OSError as error:
            die(f"{opts['document']}: {error}")
        print(json.dumps(codex_lifecycle_validation_document(
            configs, document, opts["memory_command"]), ensure_ascii=False))
        return
    die(f"unknown codex-lifecycle subcommand: {verb} (fragment|validate)")


def plan_codex_lifecycle_artifacts(plan: LifecycleRenderPlan, *, bindings_path: Path):
    """Use the P2 artifact seam for registration and its generated consumer handler."""
    return plan_claude_shaped_lifecycle_artifacts(plan, bindings_path=bindings_path)


def plan_claude_shaped_lifecycle_artifacts(plan: LifecycleRenderPlan, *, bindings_path: Path):
    """Codex/Grok share one Claude-shaped hook document plus generated lifecycle.py."""
    state_dir = _CLAUDE_SHAPED_HOOK_DIRS.get(plan.provider_id)
    if state_dir is None or not plan.green:
        raise ValueError("cannot plan refused lifecycle artifact")
    name = plan.provider_id.value
    source = ArtifactSource(f"harness.{name}.lifecycle-bindings",
                            f"packages/harness/configs/{name}/hooks/lifecycle-context-bindings.json",
                            sha256_digest(Path(bindings_path).read_bytes()))
    router_path = _CODEX_ROUTER_CATALOG_FILE
    router_source = ArtifactSource("harness.codex.router-catalog",
                                   _CODEX_ROUTER_CATALOG_PATH,
                                   sha256_digest(router_path.read_bytes()))
    identity = ArtifactAdapterIdentity(f"harness.{name}.lifecycle", _CODEX_HOOK_ADAPTER_VERSION,
                                       plan.provider_id, "1.0.0", ())
    document_path, handler_path = claude_shaped_hook_paths(plan.provider_id)
    hooks = plan_artifact_render(ArtifactRenderRequest(f"harness.{name}.lifecycle.hooks", (source,),
        ArtifactTarget(document_path, ("whole-file", ())), identity, (), {},
        lambda _request: render_codex_hooks(plan)))
    handler = plan_artifact_render(ArtifactRenderRequest(f"harness.{name}.lifecycle.handler",
        (source, router_source),
        ArtifactTarget(handler_path, ("whole-file", ())), identity, (), {},
        lambda _request: render_codex_hook_handler(state_dir=state_dir)))
    return hooks, handler


def block_codex_lifecycle(env, target, *, surfaces, trusted, repair, dry,
                          provider_id=ProviderId.CODEX):
    """Deploy Claude-shaped lifecycle as ONE managed hooks.json + handler bundle."""
    name = provider_id.value
    bindings_path = Path(env.root) / "configs" / name / "hooks/lifecycle-context-bindings.json"
    requests = tuple(LifecycleRequest(surface_id, True) for surface_id in surfaces)
    lifecycle = plan_lifecycle(
        load_catalog(default_catalog_path(env)), provider_id=provider_id,
        requests=requests, trusted=trusted, codex_bindings_path=bindings_path)
    if not lifecycle.green:
        diagnostic = lifecycle.diagnostics[0]
        die(f"{diagnostic.code}: {diagnostic.next_action}")
    artifacts = plan_codex_lifecycle_artifacts(lifecycle, bindings_path=bindings_path)
    lock_path = Path(target) / LOCK_RELATIVE_PATH
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    repair_ids = tuple(item.provenance.artifact_id for item in artifacts) if repair else ()
    plan = plan_artifact_lock(
        Path(target), artifacts, lock_bytes=lock_bytes,
        repair_artifact_ids=repair_ids, retain_unexpected_records=True)
    projection = artifact_dry_run(plan)
    print(f"{name} hooks: {len(surfaces)} surface(s) — {', '.join(sorted(surfaces))}")
    print(render_artifact_projection(projection), end="")
    if projection["exit_severity"] == "error":
        die(f"{name} lifecycle deploy refused; resolve ownership/drift or use --repair")
    if not dry:
        apply_plan(Path(target), plan)


def _read_existing_cursor_hooks(target: Path):
    hooks_path = target / ".cursor" / "hooks.json"
    if not hooks_path.exists():
        return None
    if hooks_path.is_symlink():
        raise ValueError("HARNESS_CURSOR_HOOKS_INVALID")
    try:
        value = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("HARNESS_CURSOR_HOOKS_INVALID") from exc
    if not isinstance(value, dict):
        raise ValueError("HARNESS_CURSOR_HOOKS_INVALID")
    return value


def block_cursor_lifecycle(env, target, *, surfaces, trusted, repair, dry):
    """Deploy Cursor lifecycle hooks preserving user-owned hook entries."""
    bindings_path = Path(env.root) / "configs/cursor/hooks/lifecycle-context-bindings.json"
    requests = tuple(LifecycleRequest(surface_id, True) for surface_id in surfaces)
    lifecycle = plan_lifecycle(
        load_catalog(default_catalog_path(env)), provider_id=ProviderId.CURSOR,
        requests=requests, trusted=trusted, cursor_bindings_path=bindings_path)
    if not lifecycle.green:
        diagnostic = lifecycle.diagnostics[0]
        die(f"{diagnostic.code}: {diagnostic.next_action}")
    try:
        existing_document = _read_existing_cursor_hooks(Path(target))
    except ValueError:
        die("HARNESS_CURSOR_HOOKS_INVALID: fix .cursor/hooks.json or remove it before deploy")
    artifacts = plan_cursor_lifecycle_artifacts(
        lifecycle, bindings_path=bindings_path, existing_document=existing_document)
    lock_path = Path(target) / LOCK_RELATIVE_PATH
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    repair_ids = {item.provenance.artifact_id for item in artifacts} if repair else set()
    if existing_document is not None:
        repair_ids.add("harness.cursor.lifecycle.hooks")
    plan = plan_artifact_lock(
        Path(target), artifacts, lock_bytes=lock_bytes,
        repair_artifact_ids=tuple(sorted(repair_ids)), retain_unexpected_records=True)
    projection = artifact_dry_run(plan)
    print(f"cursor hooks: {len(surfaces)} surface(s) — {', '.join(sorted(surfaces))}")
    print(render_artifact_projection(projection), end="")
    if projection["exit_severity"] == "error":
        die("Cursor lifecycle deploy refused; resolve ownership/drift or use --repair")
    if not dry:
        apply_plan(Path(target), plan)


def block_codex_observer(env, target, *, trusted, repair, dry):
    """Deploy the supported Codex lifecycle observer without replacing other package records."""
    block_codex_lifecycle(env, target, surfaces=("context.observer",),
                          trusted=trusted, repair=repair, dry=dry)


def render_codex_capture_handler() -> bytes:
    """Generated local-only capture adapter; it persists no prompt or raw hook body."""
    return b'''#!/usr/bin/env python3
import json, sys
payload = json.load(sys.stdin)
required = {"session_id", "occurred_at", "metrics"}
allowed = {"tools", "files", "workflows", "retrieval", "devloop", "maind", "codegraph", "usage", "reads", "errors"}
if (not isinstance(payload, dict) or set(payload) - (required | {"outcome"})
        or not required.issubset(payload) or not isinstance(payload["metrics"], dict)
        or not set(payload["metrics"]).issubset(allowed)
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in payload["metrics"].values())):
    sys.exit(2)
safe = {"schema": 1, "session_id": payload["session_id"], "occurred_at": payload["occurred_at"], "metrics": payload["metrics"], "outcome": payload.get("outcome", "unknown")}
print(json.dumps(safe, sort_keys=True))
'''


def plan_codex_capture_artifact(*, bindings_path: Path):
    """Create a cache-contained P2/P5-rendered Codex capture bundle, never a copied module."""
    source = ArtifactSource("harness.codex.capture-bindings",
                            "packages/harness/configs/codex/hooks/lifecycle-context-bindings.json",
                            sha256_digest(Path(bindings_path).read_bytes()))
    identity = ArtifactAdapterIdentity("harness.codex.capture", _CODEX_CAPTURE_ADAPTER_VERSION,
                                       ProviderId.CODEX, "1.0.0", ())
    return plan_artifact_render(ArtifactRenderRequest("harness.codex.capture.handler", (source,),
        ArtifactTarget(".codex/hooks/analytics-capture.py", ("whole-file", ())), identity, (), {},
        lambda _request: render_codex_capture_handler()))


def block_autoapprove(target, mode, settings_file, dry):
    """Internal documentation."""
    print(f"auto-approve: {mode or 'pass'}")
    if not mode:
        return
    if mode not in AA_MODES:
        die(f"unknown mode auto-approve: {mode} ({'|'.join(AA_MODES)})")
    set_hook_setting(target, "auto_approve", "mode", mode, dry)
    if mode == "off":
        return
    settings, f = load_settings(target, settings_file)
    cmd = "~/.claude/hooks/auto-approve/auto-approve.sh"
    added = False
    for matcher in ("Bash", "ExitPlanMode"):
        added |= add_hook(settings, "PreToolUse", matcher, cmd)
    if added:
        write_json(f, settings, dry)
    else:
        print(f"  hook auto-approve is already registered in {f}")


def block_memory(target, brain, mode, dry):
    """Internal documentation."""
    print(f"memory: {('brain=' + (brain or 'core') + ' mode=' + mode) if mode else 'pass'}")
    if not mode:
        return
    if mode not in MEM_MODES:
        die(f"unknown mode memory: {mode} ({'|'.join(MEM_MODES)})")
    brain = brain or "core"
    if mode not in MAIND_MEMORY_MODES:  # maind scopes memory by project, the brain does not apply
        set_swissknife(target, "memory_brain", brain, dry)
    set_hook_setting(target, "memory", "mode", mode, dry)
    print(f"  project attached to brain '{brain}' (mode {mode}). "
          f"Participants - ~/.claude/hooks/memory/config.json")


def block_router(target, mode, settings_file, dry):
    """Internal documentation."""
    print(f"agent-router: {mode or 'pass'}")
    if not mode:
        return
    if mode not in ROUTER_MODES:
        die(f"unknown mode router: {mode} ({'|'.join(ROUTER_MODES)})")
    set_hook_setting(target, "agent_router", "policy", mode, dry)
    if mode == "off":
        return
    settings, f = load_settings(target, settings_file)
    added = False
    added |= add_hook(settings, "UserPromptSubmit", None,
                      "python3 ~/.claude/hooks/agent-router/router.py")
    added |= add_hook(settings, "SessionStart", None,
                      "python3 ~/.claude/hooks/agent-router/session-policy.py")
    if added:
        write_json(f, settings, dry)
    else:
        print(f"  hooks agent-router are already registered in {f}")


def block_run_report(target, mode, settings_file, dry):
    """Internal documentation."""
    print(f"run-report: {mode or 'pass'}")
    if not mode:
        return
    if mode not in RUNREPORT_MODES:
        die(f"unknown mode run-report: {mode} ({'|'.join(RUNREPORT_MODES)})")
    set_hook_setting(target, "run_report", "enabled", mode, dry)
    if mode == "off":
        return


    runs_gi = target / ".claude" / "runs" / ".gitignore"
    if not runs_gi.exists():
        if dry:
            print(f"  [dry-run] would create {runs_gi} (*)")
        else:
            runs_gi.parent.mkdir(parents=True, exist_ok=True)
            runs_gi.write_text("*\n", encoding="utf-8")
            print(f"  written: {runs_gi} (runs/ is self-ignored in git)")
    settings, f = load_settings(target, settings_file)
    if add_hook(settings, "SessionEnd", None,
                "python3 ~/.claude/hooks/run-report/run-report.py"):
        write_json(f, settings, dry)
    else:
        print(f"  hook run-report is already registered in {f}")


def block_pack_guard(target, mode, settings_file, dry):
    """Internal documentation."""
    print(f"pack-guard: {mode or 'pass'}")
    if not mode:
        return
    if mode not in PACKGUARD_MODES:
        die(f"unknown mode pack-guard: {mode} ({'|'.join(PACKGUARD_MODES)})")
    set_hook_setting(target, "pack_guard", "mode", mode, dry)
    if mode == "off":
        return
    settings, f = load_settings(target, settings_file)
    cmd = "python3 ~/.claude/hooks/pack-guard/pack-guard.py"
    added = False
    for matcher in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        added |= add_hook(settings, "PreToolUse", matcher, cmd)
    if added:
        write_json(f, settings, dry)
    else:
        print(f"  hook pack-guard is already registered in {f}")


def block_plan_guard(target, mode, settings_file, dry):
    """Register the Claude PreToolUse guard for files generated by plan.py."""
    print(f"plan-guard: {mode or 'pass'}")
    if not mode:
        return
    if mode not in PACKGUARD_MODES:
        die(f"unknown mode plan-guard: {mode} ({'|'.join(PACKGUARD_MODES)})")
    set_hook_setting(target, "plan_guard", "mode", mode, dry)
    if mode == "off":
        return
    settings, f = load_settings(target, settings_file)
    cmd = "python3 ~/.claude/hooks/plan-guard/plan-guard.py"
    added = False
    for matcher in ("Edit", "Write", "MultiEdit"):
        added |= add_hook(settings, "PreToolUse", matcher, cmd)
    if added:
        write_json(f, settings, dry)
    else:
        print(f"  hook plan-guard is already registered in {f}")


def block_changelog_gate(target, mode, settings_file, dry):
    """Internal documentation."""
    print(f"changelog-gate: {mode or 'pass'}")
    if not mode:
        return
    if mode not in CHANGELOGGATE_MODES:
        die(f"unknown mode changelog-gate: {mode} ({'|'.join(CHANGELOGGATE_MODES)})")
    set_hook_setting(target, "changelog_gate", "mode", mode, dry)
    if mode == "off":
        return
    settings, f = load_settings(target, settings_file)
    cmd = "python3 ~/.claude/hooks/changelog-gate/changelog-gate.py"
    if add_hook(settings, "PreToolUse", "Bash", cmd):
        write_json(f, settings, dry)
    else:
        print(f"  hook changelog-gate is already registered in {f}")


def block_plans_dir(target, value, settings_file, dry):
    """Internal documentation."""
    print(f"plans-dir: {value or 'pass'}")
    if not value:
        return
    if value == "off":
        settings, f = load_settings(target, settings_file)
        current = settings.get("plansDirectory")
        if current is None:
            print(f"  {f}:plansDirectory not set — nothing to shoot")
            return
        if current != PLANSDIR_DEFAULT:
            warn(f"plansDirectory={current!r} — not our default, I’m not withdrawing "
                 "(respect local choice)")
            return
        del settings["plansDirectory"]
        write_json(f, settings, dry)
        return
    if Path(value).is_absolute():
        die(f"--plans-dir expects a relative directory name, received an absolute one: {value}")
    settings, _ = load_settings(target, settings_file)
    current = settings.get("plansDirectory")
    if current is not None and current != value:
        warn(f"plansDirectory is already set ({current!r}) — respect local choice, do not overwrite")
        return
    set_setting_key(target, settings_file, "plansDirectory", value, dry)


def block_output_style(env, target, name, dry):
    """Internal documentation."""
    print(f"output-style: {name or 'pass'}")
    if not name:
        return
    if name == "off":
        print("  outputStyle is not set; remove the existing one - manually in .claude/settings.local.json")
        return
    src = env.configs_dir / "output-styles" / f"{name}.md"
    if not src.exists():
        die(f"unknown output-style: {name} (no {src})")
    dst = target / ".claude" / "output-styles" / f"{name}.md"
    if dry:
        print(f"  [dry-run] would copy {src} → {dst}")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  written: {dst}")
    set_setting_key(target, "settings.local.json", "outputStyle", name, dry)
    print("  (outputStyle will be applied after /clear or new session)")


def block_statusline(target, mode, dry):
    """Internal documentation."""
    print(f"statusline: {mode or 'pass'}")
    if not mode:
        return
    if mode not in STATUSLINE_MODES:
        die(f"unknown mode statusline: {mode} ({'|'.join(STATUSLINE_MODES)})")
    if mode == "off":
        settings, f = load_settings(target, "settings.local.json")
        current = settings.get("statusLine")
        if current is None:
            print(f"  {f}:statusLine not set - nothing to remove")
            return
        if current != STATUSLINE_VALUE:
            warn(f"statusLine={current!r} — not ours, not filming (respect local choice)")
            return
        del settings["statusLine"]
        write_json(f, settings, dry)
        return
    settings, _ = load_settings(target, "settings.local.json")
    current = settings.get("statusLine")
    if current is not None and current != STATUSLINE_VALUE:
        warn(f"statusLine is already set ({current!r}) — respect local choice, do not overwrite")
        return
    set_setting_key(target, "settings.local.json", "statusLine", STATUSLINE_VALUE, dry)
    print("  (files puts `harness hooks --global`; line will appear in the next session)")


def install_global(env, dry):
    """Internal documentation."""
    script = env.apply_script
    if not script.exists():
        die(f"not found {script} — package harness damaged")
    cmd = ["bash", str(script), "--global"]
    if dry:
        cmd.append("--dry-run")
    sys.stdout.flush()
    rc = subprocess.run(cmd, check=False).returncode
    if rc:
        sys.exit(rc)


def _parse_memory_flag(raw):
    """'brain:mode' | 'mode' → (brain, mode). 'core:federation' → ('core','federation')."""
    if ":" in raw:
        brain, mode = raw.split(":", 1)
        return (brain.strip() or "core"), mode.strip()
    return "core", raw.strip()


def set_hook_setting(target, hook, key, value, dry, *, provider=None):
    """Set one `[harness.hooks]` key of the project configuration (a provider key when `provider` is given).

    The committed carrier `.swissknifeman/hooks.env` is regenerated by `sync_hooks_env`.
    """
    path = project_config_file(target)
    dotted = f"hooks.{hook}." + (f"providers.{provider}." if provider else "") + key
    if dry:
        print(f"  [dry-run] would set harness {dotted} = {value!r} in {path}")
        return
    try:
        edit_layer_file(path, "harness", dotted, value, schema=hooks_env.SCHEMA_FILE, layer="project")
    except ConfigError as error:
        die(f"{path}: {error}")
    print(f"  set: harness {dotted} = {value!r} in {path}")


def sync_hooks_env(target, dry):
    """Regenerate `.swissknifeman/hooks.env` from the project configuration."""
    path = hooks_env.carrier_path(target)
    try:
        settings = hooks_env.project_settings(target)
    except ConfigError as error:
        die(f"{project_config_file(target)}: {error}")
    text = hooks_env.render_hooks_env(settings)
    if not hooks_env.carrier_entries(settings) and not path.exists():
        print(f"  {path}: no hook modes in {project_config_file(target)} - nothing to write")
        return False
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        current = None
    if current == text:
        print(f"  {path}: up to date")
        return False
    write_text(path, text, dry)
    return True


def _sync_after_flags(target, dry):
    if dry:
        print(f"  [dry-run] would regenerate {hooks_env.carrier_path(target)} (harness hooks sync)")
        return
    sync_hooks_env(target, dry)


def cmd_hooks_state(target_arg, verb, as_json, dry):
    """`harness hooks show|sync [--target P] [--json] [--dry-run]`."""
    target = Path(target_arg or ".").expanduser().resolve()
    if verb == "sync":
        if as_json:
            die("hooks sync has no --json output; use hooks show --json")
        sync_hooks_env(target, dry)
        return
    try:
        document = hooks_env.hooks_state(target)
    except ConfigError as error:
        die(f"{project_config_file(target)}: {error}")
    if as_json:
        print(hooks_env.dumps(document))
        return
    print(f"project: {document['project']}")
    print(f"carrier: {hooks_env.carrier_path(target)} ({'stale' if document['stale'] else 'current'})")
    for name, value in hooks_env.carrier_entries(document["settings"]):
        print(f"  {name}={value}")
    for legacy in document["legacy"]:
        print(f"  legacy (read only): {legacy}")


_CODEX_OBSERVABILITY_SURFACES = (
    "lifecycle.command-log",
    "lifecycle.tool-telemetry",
    "lifecycle.run-report",
)
_CODEX_GATE_FLAGS = ("pack_guard", "plan_guard", "changelog_gate", "review_gate", "git_guardrails")
_CODEX_GATE_SURFACE = {
    "pack_guard": "lifecycle.pack-guard", "plan_guard": "lifecycle.plan-guard",
    "changelog_gate": "lifecycle.changelog-gate",
    "review_gate": "lifecycle.review-gate", "git_guardrails": "lifecycle.git-guardrails",
}
_CODEX_GATE_HOOK = {
    "lifecycle.pack-guard": "pack_guard", "lifecycle.plan-guard": "plan_guard",
    "lifecycle.changelog-gate": "changelog_gate",
    "lifecycle.review-gate": "review_gate", "lifecycle.git-guardrails": "git_guardrails",
}


def _block_codex_gates(env, target, opts, *, provider="codex"):
    """Compose one declarative Claude-shaped hooks.json deploy from every surface flag.

    Codex and Grok share the dispatcher; only the state dir (`.codex` / `.grok`) changes.
    """
    state_dir = ".codex" if provider == "codex" else ".grok"
    provider_id = ProviderId.CODEX if provider == "codex" else ProviderId.GROK
    surfaces = []
    if opts["observer"]:
        surfaces.append("context.observer")
    if opts["safe_dirs"]:
        surfaces.append("security.safe-dirs")
    if opts["daemon_safety"]:
        surfaces.append("lifecycle.daemon-safety")
    for flag in _CODEX_GATE_FLAGS:
        mode = opts[flag]
        if not mode:
            continue
        if mode not in PACKGUARD_MODES:
            die(f"unknown mode {flag.replace('_', '-')}: {mode} ({'|'.join(PACKGUARD_MODES)})")
        surface_id = _CODEX_GATE_SURFACE[flag]
        set_hook_setting(target, _CODEX_GATE_HOOK[surface_id], "mode", mode, opts["dry_run"],
                         provider=provider)
        if mode != "off":
            surfaces.append(surface_id)
    _sync_after_flags(target, opts["dry_run"])
    if not surfaces:
        die(f"provider {provider} needs at least one of: --observer / --pack-guard off|warn|strict / "
            "--plan-guard off|warn|strict / --changelog-gate off|warn|strict / --review-gate off|warn|strict / "
            "--git-guardrails off|warn|strict / --safe-dirs / --daemon-safety")
    for surface in _CODEX_OBSERVABILITY_SURFACES:
        if surface not in surfaces:
            surfaces.append(surface)
    block_codex_lifecycle(env, target, surfaces=tuple(surfaces), trusted=bool(opts["trusted"]),
                          repair=bool(opts["repair"]), dry=bool(opts["dry_run"]),
                          provider_id=provider_id)


def _block_cursor_gates(env, target, opts):
    """Cursor seam: P3 observability plus gradually enabled P4 gates."""
    unsupported = []
    if opts["observer"]:
        unsupported.append("--observer")
    if unsupported:
        die("for --provider cursor The requested flags are not supported here: "
            + ", ".join(unsupported))
    if not opts["safe_dirs"]:
        die("provider cursor requires --safe-dirs (P3/P4)")
    surfaces = [
        "security.safe-dirs",
        "lifecycle.command-log",
        "lifecycle.tool-telemetry",
        "lifecycle.run-report",
    ]
    memory = opts["memory"]
    if memory:
        brain, mode = _parse_memory_flag(memory)
        if mode not in MEM_MODES:
            die(f"unknown mode --memory: {mode} ({'|'.join(MEM_MODES)})")
        set_hook_setting(target, "memory", "mode", mode, opts["dry_run"], provider="cursor")
        set_hook_setting(target, "memory", "brain", brain, opts["dry_run"], provider="cursor")
        if mode != "off":
            surfaces.append("lifecycle.memory")
    if opts["daemon_safety"]:
        surfaces.append("lifecycle.daemon-safety")
    git_mode = opts["git_guardrails"]
    if git_mode:
        if git_mode not in PACKGUARD_MODES:
            die("unknown mode --git-guardrails: "
                + f"{git_mode} ({'|'.join(PACKGUARD_MODES)})")
        set_hook_setting(target, "git_guardrails", "mode", git_mode, opts["dry_run"], provider="cursor")
        if git_mode != "off":
            surfaces.append("lifecycle.git-guardrails")
    changelog_mode = opts["changelog_gate"]
    if changelog_mode:
        if changelog_mode not in PACKGUARD_MODES:
            die("unknown mode --changelog-gate: "
                + f"{changelog_mode} ({'|'.join(PACKGUARD_MODES)})")
        set_hook_setting(target, "changelog_gate", "mode", changelog_mode, opts["dry_run"], provider="cursor")
        if changelog_mode != "off":
            surfaces.append("lifecycle.changelog-gate")
    pack_mode = opts["pack_guard"]
    if pack_mode:
        if pack_mode not in PACKGUARD_MODES:
            die("unknown mode --pack-guard: "
                + f"{pack_mode} ({'|'.join(PACKGUARD_MODES)})")
        set_hook_setting(target, "pack_guard", "mode", pack_mode, opts["dry_run"], provider="cursor")
        if pack_mode != "off":
            surfaces.append("lifecycle.pack-guard")
    plan_mode = opts["plan_guard"]
    if plan_mode:
        if plan_mode not in PACKGUARD_MODES:
            die("unknown mode --plan-guard: "
                + f"{plan_mode} ({'|'.join(PACKGUARD_MODES)})")
        set_hook_setting(target, "plan_guard", "mode", plan_mode, opts["dry_run"], provider="cursor")
        if plan_mode != "off":
            surfaces.append("lifecycle.plan-guard")
    review_mode = opts["review_gate"]
    if review_mode:
        if review_mode not in PACKGUARD_MODES:
            die("unknown mode --review-gate: "
                + f"{review_mode} ({'|'.join(PACKGUARD_MODES)})")
        set_hook_setting(target, "review_gate", "mode", review_mode, opts["dry_run"], provider="cursor")
        if review_mode != "off":
            surfaces.append("lifecycle.review-gate")
    _sync_after_flags(target, opts["dry_run"])
    block_cursor_lifecycle(env, target, surfaces=tuple(surfaces),
                           trusted=bool(opts["trusted"]), repair=bool(opts["repair"]),
                           dry=bool(opts["dry_run"]))


def block_plan_regen(target, mode, settings_file, dry):
    """Register the Claude PostToolUse hook that checks and re-renders a plan after a JSON edit."""
    print(f"plan-regen: {mode or 'pass'}")
    if not mode:
        return
    if mode not in PLANREGEN_MODES:
        die(f"unknown mode plan-regen: {mode} ({'|'.join(PLANREGEN_MODES)})")
    set_hook_setting(target, "plan_regen", "mode", mode, dry)
    if mode == "off":
        return
    settings, f = load_settings(target, settings_file)
    cmd = "python3 ~/.claude/hooks/plan-regen/plan-regen.py"
    added = False
    for matcher in ("Edit", "Write", "MultiEdit"):
        added |= add_hook(settings, "PostToolUse", matcher, cmd)
    if added:
        write_json(f, settings, dry)
    else:
        print(f"  hook plan-regen is already registered in {f}")


def cmd_hooks(env, argv):
    if argv and argv[0] == "codex-lifecycle":
        return cmd_codex_lifecycle(env, argv[1:])
    if argv and argv[0] in ("sync", "show"):
        state = parse_flags(argv[1:], {"--target": "str", "--json": "bool", "--dry-run": "bool"})
        if state["help"]:
            print("harness hooks sync [--target P] [--dry-run]\n"
                  "harness hooks show [--target P] [--json]")
            return
        return cmd_hooks_state(state["target"], argv[0], state["json"], state["dry_run"])
    opts = parse_flags(argv, {
        "--target": "str", "--auto-approve": "str", "--memory": "str",
        "--router": "str", "--run-report": "str", "--pack-guard": "str",
        "--plan-guard": "str", "--plan-regen": "str",
        "--changelog-gate": "str", "--review-gate": "str", "--git-guardrails": "str",
        "--safe-dirs": "bool", "--daemon-safety": "bool",
        "--output-style": "str", "--plans-dir": "str", "--statusline": "str",
        "--file": "str",
        "--provider": "str", "--observer": "bool", "--trusted": "bool",
        "--repair": "bool", "--global": "bool", "--dry-run": "bool",
    })
    if opts["help"]:
        print("harness hooks sync|show [--target P] [--json] [--dry-run]   (hook modes: .swissknifeman/hooks.env)\n"
              "harness hooks [--global] [--target P] [--auto-approve "
              f"{'|'.join(AA_MODES)}] [--memory BRAIN:{'|'.join(MEM_MODES)}] "
              f"[--router {'|'.join(ROUTER_MODES)}] "
              f"[--run-report {'|'.join(RUNREPORT_MODES)}] "
              f"[--pack-guard {'|'.join(PACKGUARD_MODES)}] "
              f"[--plan-guard {'|'.join(PACKGUARD_MODES)}] "
              f"[--plan-regen {'|'.join(PLANREGEN_MODES)}] "
              f"[--changelog-gate {'|'.join(CHANGELOGGATE_MODES)}] "
              "[--output-style lean|off] "
              "[--plans-dir plans|off] "
              f"[--statusline {'|'.join(STATUSLINE_MODES)}] "
              "[--provider codex|grok [--observer] [--pack-guard off|warn|strict] [--plan-guard off|warn|strict] "
              "[--changelog-gate off|warn|strict] [--review-gate off|warn|strict] "
              "[--git-guardrails off|warn|strict] [--safe-dirs] [--daemon-safety] "
              "| --provider cursor [--safe-dirs] "
              "[--memory BRAIN:maind|file|federation|agentmemory|off] "
              "[--daemon-safety] [--git-guardrails off|warn|strict] "
              "[--changelog-gate off|warn|strict] [--pack-guard off|warn|strict] "
              "[--plan-guard off|warn|strict] [--review-gate off|warn|strict] "
              "[--trusted] [--repair]] "
              "[--file settings.json|settings.local.json] [--dry-run]")
        return
    if opts["global"]:
        install_global(env, opts["dry_run"])
        return
    if not opts["target"]:
        die("needed --target P (or --global)")
    # Public CLI accepts a convenient relative target, while the shared
    # artifact lock deliberately accepts only an explicit absolute root.
    target = Path(opts["target"]).expanduser().resolve()
    if opts["provider"]:
        if opts["provider"] in ("codex", "grok"):
            _block_codex_gates(env, target, opts, provider=opts["provider"])
        elif opts["provider"] == "cursor":
            _block_cursor_gates(env, target, opts)
        else:
            die("is only supported --provider codex|cursor|grok")
        return
    if not (opts["auto_approve"] or opts["memory"] or opts["router"]
            or opts["run_report"] or opts["pack_guard"] or opts["changelog_gate"]
            or opts["output_style"] or opts["plans_dir"] or opts["statusline"]
            or opts["plan_guard"] or opts["plan_regen"]):
        die("needs at least one of: --auto-approve MODE / --memory BRAIN:MODE / "
            "--router MODE / --run-report on|off / --pack-guard off|warn|strict / "
            "--changelog-gate off|warn|strict / --plan-guard off|warn|strict / "
            "--plan-regen on|off / --output-style lean|off / --plans-dir plans|off / "
            "--statusline context|off / --global")
    settings_file = opts["file"] or "settings.json"
    if opts["auto_approve"]:
        block_autoapprove(target, opts["auto_approve"], settings_file, opts["dry_run"])
    if opts["memory"]:
        brain, mode = _parse_memory_flag(opts["memory"])
        block_memory(target, brain, mode, opts["dry_run"])
    if opts["router"]:
        block_router(target, opts["router"], settings_file, opts["dry_run"])
    if opts["run_report"]:
        block_run_report(target, opts["run_report"], settings_file, opts["dry_run"])
    if opts["pack_guard"]:
        block_pack_guard(target, opts["pack_guard"], settings_file, opts["dry_run"])
    if opts["changelog_gate"]:
        block_changelog_gate(target, opts["changelog_gate"], settings_file, opts["dry_run"])
    if opts["output_style"]:
        block_output_style(env, target, opts["output_style"], opts["dry_run"])
    if opts["plans_dir"]:
        block_plans_dir(target, opts["plans_dir"], settings_file, opts["dry_run"])
    if opts["statusline"]:
        block_statusline(target, opts["statusline"], opts["dry_run"])
    if opts["plan_guard"]:
        block_plan_guard(target, opts["plan_guard"], settings_file, opts["dry_run"])
    if opts["plan_regen"]:
        block_plan_regen(target, opts["plan_regen"], settings_file, opts["dry_run"])
    if (opts["auto_approve"] or opts["memory"] or opts["router"] or opts["run_report"]
            or opts["pack_guard"] or opts["changelog_gate"] or opts["plan_guard"] or opts["plan_regen"]):
        _sync_after_flags(target, opts["dry_run"])
