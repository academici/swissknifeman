#!/usr/bin/env python3
import argparse, datetime, importlib.util, json, os, re, shlex, shutil, subprocess, sys
from pathlib import Path

_SURFACE_EVENTS = {
    "context.observer": "SessionStart",
    "lifecycle.command-log": "PreToolUse",
    "lifecycle.run-report": "SessionEnd",
    "lifecycle.router": "UserPromptSubmit",
    "lifecycle.memory": "SessionStart",
    "lifecycle.pack-guard": "PreToolUse",
    "lifecycle.changelog-gate": "PreToolUse",
    "lifecycle.review-gate": "SubagentStop",
    "security.safe-dirs": "PreToolUse",
    "lifecycle.daemon-safety": "PreToolUse",
    "lifecycle.git-guardrails": "PreToolUse",
    "lifecycle.terminal-admission": "Stop",
}
_EVENT_FIELDS = {
    "SessionStart": ("source",),
    "PreToolUse": ("tool_name", "tool_input"),
    "SessionEnd": ("reason",),
    "UserPromptSubmit": ("prompt",),
    "SubagentStop": ("agent_type",),
    "Stop": ("stop_hook_active", "last_assistant_message"),
}
_GATE_MODES = ("off", "warn", "strict")


def _read_mode(cwd, filename):
    """MODE from <cwd>/.codex/<filename> (harness hooks --provider codex writes it).
    Missing/unreadable/unknown value -> off (safe default, matches the Claude-side
    gates and the phase's explicit "inactive by default" requirement)."""
    if not cwd:
        return "off"
    f = Path(cwd) / ".codex" / filename
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
            allowed = ("on", "off") if filename == "terminal-admission.env.ini" else _GATE_MODES
            mode = value if value in allowed else "off"
    return mode
_ROUTER_CATALOG = [{"name": "task:design", "weight": 1, "keywords": ["спроектир", "проектир", "дизайн", "архитектур", "design", "architecture", "adr", "распланируй", "продумай", "схему", "модель данных", "concept"]}, {"name": "task:dev", "weight": 1, "keywords": ["сделай", "добавь", "реализуй", "построй", "напиши", "внедри", "build", "implement", "feature", "фича", "эндпоинт", "endpoint", "команду", "миграци", "интеграци"]}, {"name": "task:research", "weight": 1, "keywords": ["исследуй", "research", "сравни", "compare", "разузнай", "investigate", "актуально", "best practice", "варианты", "какой лучше", "изучи"]}, {"name": "task:review", "weight": 1, "keywords": ["ревью", "отревьюй", "review", "audit", "аудит", "diff", "pr", "проверь код", "code review", "посмотри дифф"]}, {"name": "task:fix", "weight": 1, "keywords": ["почини", "fix", "баг", "bug", "опечатк", "typo", "поправь", "мелкая правка", "small fix", "сломал"]}]
_ROUTER_HINT_TEMPLATE = '[intent-router] bias (non-authoritative): top={name} score={score}{runners}'
_ROUTER_THRESHOLD = 2


def _observer(payload):
    print(json.dumps({"systemMessage": "[harness observer] read-only policy active"}))


def _command_log(payload):
    log_dir = Path.home() / ".codex" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        tool_input = payload.get("tool_input") or {}
        entry = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "cwd": payload.get("cwd", ""), "session": payload.get("session_id", ""),
                 "command": tool_input.get("command"), "description": tool_input.get("description")}
        with (log_dir / "bash-commands.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _run_report(payload):
    cwd = payload.get("cwd")
    if not cwd:
        return
    runs_dir = Path(cwd) / ".codex" / "runs"
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        gitignore = runs_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")
        record = {"schema": 1, "session_id": payload.get("session_id", ""), "cwd": cwd,
                  "reason": payload.get("reason", ""),
                  "transcript_path": payload.get("transcript_path")}
        target = runs_dir / (str(payload.get("session_id") or "session") + ".json")
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, target)
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
    runners = ", ".join(f"{name} ({score})" for name, score in scored[1:3])
    try:
        hint = _ROUTER_HINT_TEMPLATE.format(
            name=top_name, score=top_score,
            runners=("; runners-up: " + runners) if runners else "")
    except (KeyError, IndexError):
        return
    print(json.dumps({"systemMessage": hint}))


def _memory(payload):
    cwd = payload.get("cwd")
    mode, brain = "maind", "core"
    if cwd:
        ini = Path(cwd) / ".codex" / "memory.env.ini"
        try:
            for line in ini.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                if key == "MODE":
                    mode = value
                elif key == "BRAIN":
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
            print(json.dumps({"systemMessage": "[harness memory] " + result.stdout.strip()}))
    except Exception:
        pass


def _managed_pack_files(cwd):
    """target (project-relative) -> pack name, from .claude/agent-pack.lock.json — the
    SAME lock a Codex session sees when it edits a Claude-onboarded project's managed
    assets (codex-parity-verdicts-v1.md §3.5). Without user_owned entries."""
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
    tool_input = payload.get("tool_input") or {}
    try:
        haystack = json.dumps(tool_input, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    hit = next((path for path in managed if path in haystack), None)
    if hit is None:
        return
    pack = managed[hit]
    msg = (f"pack-guard: apply_patch touches a file managed by pack '{pack}' "
          f"(swissknifeman:generated) — edit the pack overlay or accept the change "
          f"through 'harness agent-packs upgrade': {hit}")
    if mode == "strict":
        sys.stderr.write(msg + "\n")
        sys.exit(2)
    print(json.dumps({"systemMessage": "[warn] " + msg}))


_CHANGELOG_TYPE_RE = re.compile(r"^(feat|fix|perf|refactor)(\([^)]*\))?!?:\s")
_CHANGELOG_NAME_RE = re.compile(r"changelog", re.IGNORECASE)
_CHANGELOG_SEGMENT_RE = re.compile(r"&&|\|\||;|\|")


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
    tool_input = payload.get("tool_input") or {}
    messages = _commit_messages(tool_input.get("command"))
    if not messages:
        return
    if "[changelog-skip]" in "\n".join(messages):
        return
    m = _CHANGELOG_TYPE_RE.match(messages[0])
    if not m:
        return
    files = _git_lines(cwd, "ls-files")
    if not files or not any(_CHANGELOG_NAME_RE.search(f) for f in files):
        return
    staged = _git_lines(cwd, "diff", "--cached", "--name-only")
    if staged and any(_CHANGELOG_NAME_RE.search(f) for f in staged):
        return
    reason = (f"changelog-gate: commit '{m.group(1)}:' is content-bearing but "
             f"[Unreleased] is untouched. Stage a CHANGELOG entry or add [changelog-skip].")
    if mode == "strict":
        sys.stderr.write(reason + "\n")
        sys.exit(2)
    print(json.dumps({"systemMessage": "[warn] " + reason}))


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
    state_path = Path(cwd) / ".codex" / "review-gate.state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
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
    reason = f"review-gate: check failed after subagent stop (mode={mode}).\n{body}"
    if mode == "strict" and attempts < _REVIEW_GATE_MAX_ATTEMPTS:
        if not isinstance(state, dict):
            state = {}
        state[key] = attempts + 1
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state), encoding="utf-8")
        except OSError:
            pass
        sys.stderr.write(reason + "\n")
        sys.exit(2)   # forces the subagent to continue — does not cancel it (D88)
    print(json.dumps({"systemMessage": reason}))


_RM_HEAD_RE = re.compile(r"\b(rm|rmdir)\b")


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
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not _RM_HEAD_RE.search(command):
        return
    root = _find_repo_root()
    if root is None:
        sys.stderr.write("security.safe-dirs: refusing rm/rmdir — harness checkout "
                         "unreachable from this session\n")
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
        sys.stderr.write(f"security.safe-dirs: refusing rm/rmdir — '{command}' is not "
                         f"covered by the safe-dirs allowlist\n")
        sys.exit(2)


_DAEMON_SAFETY_PATTERNS = tuple(re.compile(p) for p in (
    r"pkill.*(perplexity|playwright|chromium|chrome)",
    r"killall.*(perplexity|playwright|chromium|chrome)",
    r"kill +-9.*(perplexity|playwright|chromium)",
    r"rm .*Singleton", r"rm .*\.playwright/(profile|profiles)",
    r"rm .*perplexity-web-mcp", r"rm .*profile\.lock", r"rm .*perplexity.*\.sock"))


def _daemon_safety(payload):
    if payload.get("tool_name") != "Bash" or os.environ.get("PERPLEXITY_DAEMON_GUARD") == "off":
        return
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str):
        return
    for pattern in _DAEMON_SAFETY_PATTERNS:
        if pattern.search(command):
            sys.stderr.write(f"BLOCKED (daemon-safety): '{command}' matches a shared-daemon "
                             f"destructive pattern. Reuse the live daemon or wait for it to be "
                             f"idle. One-time bypass: PERPLEXITY_DAEMON_GUARD=off.\n")
            sys.exit(2)


_GIT_GUARDRAILS_PATTERNS = tuple(re.compile(p) for p in (
    r"git push", r"git reset --hard", r"git clean -fd", r"git clean -f", r"git branch -D",
    r"git checkout \.", r"git restore \.", r"push --force", r"push --force-with-lease",
    r"reset --hard", r"rebase --onto"))


def _git_guardrails(payload):
    if payload.get("tool_name") != "Bash":
        return
    cwd = payload.get("cwd")
    mode = _read_mode(cwd, "git-guardrails.env.ini")
    if mode == "off" or not cwd:
        return
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str):
        return
    for pattern in _GIT_GUARDRAILS_PATTERNS:
        if pattern.search(command):
            reason = f"git-guardrails: '{command}' matches dangerous pattern '{pattern.pattern}'."
            if mode == "strict":
                sys.stderr.write(reason + "\n")
                sys.exit(2)
            print(json.dumps({"systemMessage": "[warn] " + reason}))
            return


def _terminal_admission(payload):
    """Thin Stop adapter: P4.1 remains the only terminal-policy owner."""
    cwd = payload.get("cwd")
    if _read_mode(cwd, "terminal-admission.env.ini") != "on" or not cwd:
        return
    request = payload.get("terminal_admission")
    if not isinstance(request, dict) or not request.get("applicable"):
        return
    required = ("plan", "subject", "command", "run_id", "task_session", "continuity_json")
    if any(not isinstance(request.get(key), str) or not request[key] for key in required):
        print(json.dumps({"decision": "block", "reason": "TERMINAL_ADMISSION_CONTEXT_INVALID"})); return
    cli = Path(cwd) / "packages/task/scripts/plan-terminal-admission.py"
    if not cli.is_file():
        print(json.dumps({"decision": "block", "reason": "TASK_TERMINAL_ADMISSION_UNAVAILABLE"})); return
    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        print(json.dumps({"decision": "block", "reason": "TERMINAL_MESSAGE_UNAVAILABLE"})); return
    command = [sys.executable, str(cli), "check", "--state-dir", str(Path(cwd) / ".swissknifeman/terminal-admission"),
               "--plan", request["plan"], "--subject", request["subject"], "--command", request["command"],
               "--run-id", request["run_id"], "--task-session", request["task_session"], "--provider", "codex",
               "--provider-session", payload.get("session_id", ""), "--turn-id", payload.get("turn_id", ""),
               "--continuity-json", request["continuity_json"], "--message", message,
               "--plan-dir", str(Path(cwd) / "plans" / request["plan"])]
    result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    try:
        verdict = json.loads(result.stdout)
    except (TypeError, ValueError):
        verdict = {"final_allowed": False, "reason": "TERMINAL_ADMISSION_VERIFIER_FAILED"}
    if not verdict.get("final_allowed"):
        print(json.dumps({"decision": "block", "reason": str(verdict.get("reason") or "TERMINAL_ADMISSION_REFUSED")}))


_HANDLERS = {
    "context.observer": _observer,
    "lifecycle.command-log": _command_log,
    "lifecycle.run-report": _run_report,
    "lifecycle.router": _router,
    "lifecycle.memory": _memory,
    "lifecycle.pack-guard": _pack_guard,
    "lifecycle.changelog-gate": _changelog_gate,
    "lifecycle.review-gate": _review_gate,
    "security.safe-dirs": _safe_dirs,
    "lifecycle.daemon-safety": _daemon_safety,
    "lifecycle.git-guardrails": _git_guardrails,
    "lifecycle.terminal-admission": _terminal_admission,
}

parser = argparse.ArgumentParser()
parser.add_argument("--surface", required=True)
args = parser.parse_args()
if args.surface not in _SURFACE_EVENTS:
    sys.exit(2)
try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError):
    sys.exit(2)
if not isinstance(payload, dict):
    sys.exit(2)
event = _SURFACE_EVENTS[args.surface]
required = {"session_id", "cwd", "hook_event_name", "model"}
if event == "SessionStart":
    required.add("permission_mode")
required.update(_EVENT_FIELDS.get(event, ()))
if not required.issubset(payload) or payload["hook_event_name"] != event:
    sys.exit(2)
_HANDLERS[args.surface](payload)
