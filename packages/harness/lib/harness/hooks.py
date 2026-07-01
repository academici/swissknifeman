"""hooks — включить хуки Claude Code по проекту / поставить файлы хуков глобально.

per-project: пишет <project>/.claude/auto-approve.env.ini + memory.env.ini и
регистрирует хук auto-approve в settings (merge-only). global: ставит файлы хуков
в ~/.claude/hooks/ через scripts/apply-permissions.sh --global."""
import subprocess
import sys
from pathlib import Path

from .common import die, parse_flags
from .settings import add_hook, load_settings, set_swissknife, write_json, write_text

AA_MODES = ("strict", "permissive", "bypass", "off")
MEM_MODES = ("file", "federation", "agentmemory", "off")
ROUTER_MODES = ("propose", "auto_dispatch", "off")
RUNREPORT_MODES = ("on", "off")


def block_autoapprove(target, mode, settings_file, dry):
    """Записать auto-approve.env.ini + зарегистрировать хук (Bash/ExitPlanMode)."""
    print(f"auto-approve: {mode or 'пропуск'}")
    if not mode:
        return
    if mode not in AA_MODES:
        die(f"неизвестный режим auto-approve: {mode} ({'|'.join(AA_MODES)})")
    write_text(target / ".claude" / "auto-approve.env.ini", f"MODE={mode}\n", dry)
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
        print(f"  хук auto-approve уже зарегистрирован в {f}")


def block_memory(target, brain, mode, dry):
    """Присоединить проект к brain: .swissknife.json:memory_brain + memory.env.ini."""
    print(f"memory: {('brain=' + (brain or 'core') + ' mode=' + mode) if mode else 'пропуск'}")
    if not mode:
        return
    if mode not in MEM_MODES:
        die(f"неизвестный режим memory: {mode} ({'|'.join(MEM_MODES)})")
    brain = brain or "core"
    set_swissknife(target, "memory_brain", brain, dry)
    write_text(target / ".claude" / "memory.env.ini", f"MODE={mode}\n", dry)
    print(f"  проект присоединён к brain '{brain}' (режим {mode}). "
          f"Состав участников — ~/.claude/hooks/memory/config.json")


def block_router(target, mode, settings_file, dry):
    """Записать agent-router.env.ini + зарегистрировать пару хуков intent-router:
    UserPromptSubmit (per-turn bias) + SessionStart (статическая политика). off → без хуков."""
    print(f"agent-router: {mode or 'пропуск'}")
    if not mode:
        return
    if mode not in ROUTER_MODES:
        die(f"неизвестный режим router: {mode} ({'|'.join(ROUTER_MODES)})")
    write_text(target / ".claude" / "agent-router.env.ini", f"POLICY={mode}\n", dry)
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
        print(f"  хуки agent-router уже зарегистрированы в {f}")


def block_run_report(target, mode, settings_file, dry):
    """Записать run-report.env.ini + зарегистрировать SessionEnd-хук архивного захвата прогона.
    on → пишет ENABLED=on + регистрирует хук; off → пишет ENABLED=off (kill-switch без снятия
    хука — merge-only не удаляет чужие записи). Хук пишет <project>/.claude/runs/<sid>.json."""
    print(f"run-report: {mode or 'пропуск'}")
    if not mode:
        return
    if mode not in RUNREPORT_MODES:
        die(f"неизвестный режим run-report: {mode} ({'|'.join(RUNREPORT_MODES)})")
    write_text(target / ".claude" / "run-report.env.ini",
               f"ENABLED={mode}\nRUNS_KEEP=30\n", dry)
    if mode == "off":
        return
    # runs/ — эфемерные машинно-локальные артефакты: само-игнорируемый каталог, чтобы
    # run-report'ы не засоряли git status (и не ломали 'dirty tree' в maind analyze).
    runs_gi = target / ".claude" / "runs" / ".gitignore"
    if not runs_gi.exists():
        if dry:
            print(f"  [dry-run] создал бы {runs_gi} (*)")
        else:
            runs_gi.parent.mkdir(parents=True, exist_ok=True)
            runs_gi.write_text("*\n", encoding="utf-8")
            print(f"  записано: {runs_gi} (runs/ само-игнорируется в git)")
    settings, f = load_settings(target, settings_file)
    if add_hook(settings, "SessionEnd", None,
                "python3 ~/.claude/hooks/run-report/run-report.py"):
        write_json(f, settings, dry)
    else:
        print(f"  хук run-report уже зарегистрирован в {f}")


def install_global(env, dry):
    """Поставить файлы хуков (auto-approve/memory/notify/log) в ~/.claude/hooks/."""
    script = env.apply_script
    if not script.exists():
        die(f"не найден {script} — пакет harness повреждён")
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


def cmd_hooks(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--auto-approve": "str", "--memory": "str",
        "--router": "str", "--run-report": "str", "--file": "str",
        "--global": "bool", "--dry-run": "bool",
    })
    if opts["help"]:
        print("harness hooks [--global] [--target P] [--auto-approve "
              f"{'|'.join(AA_MODES)}] [--memory BRAIN:{'|'.join(MEM_MODES)}] "
              f"[--router {'|'.join(ROUTER_MODES)}] "
              f"[--run-report {'|'.join(RUNREPORT_MODES)}] "
              "[--file settings.json|settings.local.json] [--dry-run]")
        return
    if opts["global"]:
        install_global(env, opts["dry_run"])
        return
    if not opts["target"]:
        die("нужен --target P (или --global)")
    target = Path(opts["target"]).expanduser()
    if not (opts["auto_approve"] or opts["memory"] or opts["router"] or opts["run_report"]):
        die("нужен хотя бы один из: --auto-approve MODE / --memory BRAIN:MODE / "
            "--router MODE / --run-report on|off / --global")
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
