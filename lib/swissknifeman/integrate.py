"""integrate — визард интеграции swissknifeman в проект.

Проходит чеклист «выбери, что хочешь из максимального функционала» и применяет
выбранное, переиспользуя существующие команды: do_connect/do_vendor (скиллы),
apply-permissions.sh (permissions), generate_hub (хаб) + пишет per-project хук-JSON
и .swissknife.json. Безопасно: --dry-run, merge-only, бэкап *.bak, confirm.

Блоки: пререквизиты → скиллы → permissions → auto-approve → memory → hub → brain.
"""
import json
import shutil
import subprocess
import sys

from .common import die, parse_flags
from .config import autodetect, load_config, resolve_target
from .connect import do_connect
from .vendor import do_vendor
from .hub import generate_hub
from .topology import cmd_topology

# Бандл = пред-ответы на чеклист. custom → спрашиваем интерактивно.
BUNDLES = {
    "minimal":     {"skills": "connect", "perms": False, "autoapprove": None,
                    "memory": None, "hub": False, "brain": False},
    "recommended": {"skills": "connect", "perms": True, "autoapprove": "strict",
                    "memory": None, "hub": True, "brain": False},
    "full":        {"skills": "connect", "perms": True, "autoapprove": "strict",
                    "memory": "federation", "hub": True, "brain": True},
}
AA_MODES = ("strict", "permissive", "bypass", "off")
MEM_MODES = ("file", "federation", "agentmemory", "off")


# --- prompt helpers -----------------------------------------------------------
def _interactive():
    return sys.stdin.isatty()


def _yn(prompt, default):
    suffix = "[Y/n]" if default else "[y/N]"
    ans = input(f"{prompt} {suffix} ").strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes", "д", "да")


def _ask_yn(prompt, default, interactive):
    return _yn(prompt, default) if interactive else default


def _ask_choice(prompt, options, default, interactive):
    if not interactive:
        return default
    opts = "/".join(o if o != default else o.upper() for o in options)
    while True:
        ans = input(f"{prompt} ({opts}) [{default}]: ").strip().lower()
        if not ans:
            return default
        if ans in options:
            return ans
        print(f"  выбери из: {', '.join(options)}")


def _ask_text(prompt, default, interactive):
    if not interactive:
        return default
    return input(f"{prompt} [{default}]: ").strip() or default


# --- settings / file writers (merge-only, dry-run aware) ----------------------
def _write_json(path, data, dry):
    if dry:
        print(f"  [dry-run] записал бы {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, f"{path}.bak")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"  записано: {path}")


def _write_text(path, text, dry):
    if dry:
        print(f"  [dry-run] записал бы {path} ({text!r})")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, f"{path}.bak")
    path.write_text(text, encoding="utf-8")
    print(f"  записано: {path}")


def _load_settings(target, fname):
    f = target / ".claude" / fname
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")), f
        except json.JSONDecodeError as e:
            die(f"{f}: невалидный JSON: {e}")
    return {}, f


def _add_hook(settings, event, matcher, command):
    """Добавить PreToolUse/Notification-хук, merge-only. True если добавлен."""
    entries = settings.setdefault("hooks", {}).setdefault(event, [])
    for e in entries:
        if e.get("matcher") == matcher and \
                any(h.get("command") == command for h in e.get("hooks", [])):
            return False
    entry = {"hooks": [{"type": "command", "command": command}]}
    if matcher:
        entry = {"matcher": matcher, **entry}
    entries.append(entry)
    return True


def _set_swissknife(target, key, value, dry):
    f = target / ".swissknife.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{f}: невалидный JSON: {e}")
    if data.get(key) == value:
        print(f"  .swissknife.json:{key} уже = {value}")
        return
    data[key] = value
    _write_json(f, data, dry)


# --- blocks -------------------------------------------------------------------
def _block_prereqs(env, dry, interactive):
    print("\n[0] Пререквизиты (machine-level, one-time)")
    topo = env.home / ".swissknifeman" / "topology.json"
    if topo.exists():
        print("  ✓ топология настроена")
    else:
        print("  ✗ нет ~/.swissknifeman/topology.json — координатор и память без "
              "него резолвят узлы по слабым дефолтам")
        if not dry and interactive and _yn("  Запустить topology init сейчас?", False):
            cmd_topology(env, ["init"])
    hooks = env.home / ".claude" / "hooks"
    have = all((hooks / d).exists() for d in ("notify", "auto-approve", "memory"))
    if have:
        print("  ✓ файлы хуков установлены (~/.claude/hooks/)")
    else:
        print("  ✗ файлы хуков не установлены — нужно ./scripts/apply-permissions.sh --global")
        script = env.root / "scripts" / "apply-permissions.sh"
        if not dry and interactive and script.exists() and \
                _yn("  Установить файлы хуков глобально сейчас?", False):
            sys.stdout.flush()
            subprocess.run(["bash", str(script), "--global"], check=False)


def _block_skills(env, target, choices, dry):
    ch = choices["skills"]
    print(f"\n[1] Скиллы: {ch or 'пропуск'}")
    if not ch:
        return
    opts = {"dry_run": dry, "hub": choices["hub"]}
    if ch == "connect":
        do_connect(env, target, opts)
    elif ch == "vendor":
        opts["agent"] = choices.get("skills_agent") or "cursor"
        do_vendor(env, target, opts)


def _block_perms(env, target, choices, dry):
    if not choices["perms"]:
        print("\n[2] Permissions: пропуск")
        return
    print("\n[2] Permissions")
    script = env.root / "scripts" / "apply-permissions.sh"
    if not script.exists():
        print("  пропуск: scripts/apply-permissions.sh не найден")
        return
    cmd = ["bash", str(script), "--target", str(target)]
    if choices.get("perms_presets"):
        cmd += ["--preset", choices["perms_presets"]]
    if dry:
        cmd.append("--dry-run")
    sys.stdout.flush()
    subprocess.run(cmd, check=False)


def _block_autoapprove(target, choices, dry):
    mode = choices["autoapprove"]
    print(f"\n[3] auto-approve: {mode or 'пропуск'}")
    if not mode:
        return
    _write_text(target / ".claude" / "auto-approve.env.ini", f"MODE={mode}\n", dry)
    if mode == "off":
        return
    fname = choices["settings_file"]
    settings, f = _load_settings(target, fname)
    cmd = "~/.claude/hooks/auto-approve/auto-approve.sh"
    added = False
    for matcher in ("Bash", "ExitPlanMode"):
        added |= _add_hook(settings, "PreToolUse", matcher, cmd)
    if added:
        _write_json(f, settings, dry)
    else:
        print(f"  хук auto-approve уже зарегистрирован в {f}")


def _block_memory(env, target, choices, dry):
    brain_mode = choices["memory"]
    print(f"\n[4] memory: {('brain=' + choices.get('memory_brain', 'core') + ' mode=' + brain_mode) if brain_mode else 'пропуск'}")
    if not brain_mode:
        return
    brain = choices.get("memory_brain") or "core"
    _set_swissknife(target, "memory_brain", brain, dry)
    _write_text(target / ".claude" / "memory.env.ini", f"MODE={brain_mode}\n", dry)
    print(f"  проект присоединён к brain '{brain}' (режим {brain_mode}). "
          f"Состав участников — ~/.claude/hooks/memory/config.json")


def _block_hub(env, target, choices, dry):
    # Хаб уже сгенерён внутри connect/vendor, если skills+hub. Иначе — отдельно.
    if not choices["hub"] or choices["skills"]:
        return
    print("\n[5] Hub")
    if dry:
        print("  [dry-run] сгенерировал бы хаб (CLAUDE.md / .ai)")
        return
    try:
        generate_hub(env, target)
    except Exception as e:  # noqa: BLE001 — хаб не должен валить визард
        print(f"  пропуск хаба: {e}")


def _block_brain(target, choices):
    if not choices["brain"]:
        return
    print("\n[6] Brain docs-sync (подсказка — настраивается со стороны волта)")
    print(f"  В заметке проекта в Brain-волте добавь во frontmatter:")
    print(f"      repo: {target}")
    print(f"  Затем: brain status <project> / brain sync <project>")


# --- choices assembly ---------------------------------------------------------
def _gather(env, target, opts, bundle, interactive):
    base = dict(BUNDLES.get(bundle, BUNDLES["recommended"]))
    base["settings_file"] = opts.get("file") or "settings.json"
    base["memory_brain"] = "core"
    if bundle != "custom":
        # авто-пресеты permissions (autodetect внутри apply-permissions при пустом)
        base["perms_presets"] = ""
        return base

    # custom — интерактивный чеклист
    detected = autodetect(target)
    print(f"Проект: {target}  (autodetect: {detected})")
    ch = {"settings_file": opts.get("file") or "settings.json", "memory_brain": "core"}
    ch["skills"] = _ask_choice("Канал скиллов", ("connect", "vendor", "skip"),
                               "connect", interactive)
    if ch["skills"] == "skip":
        ch["skills"] = None
    if ch["skills"] == "vendor":
        ch["skills_agent"] = _ask_choice("  агент", ("cursor", "generic", "claude"),
                                         "cursor", interactive)
    ch["perms"] = _ask_yn("Применить permissions-пресеты (autodetect)?", True, interactive)
    ch["perms_presets"] = ""
    ch["autoapprove"] = _ask_choice("auto-approve режим", AA_MODES + ("skip",),
                                    "strict", interactive)
    if ch["autoapprove"] == "skip":
        ch["autoapprove"] = None
    join_mem = _ask_yn("Присоединить проект к общему мозгу (memory)?", False, interactive)
    if join_mem:
        ch["memory_brain"] = _ask_text("  brain", "core", interactive)
        ch["memory"] = _ask_choice("  режим", MEM_MODES, "federation", interactive)
    else:
        ch["memory"] = None
    ch["hub"] = _ask_yn("Сгенерировать хаб скиллов (CLAUDE.md / .ai)?", True, interactive)
    ch["brain"] = _ask_yn("Показать подсказку по brain docs-sync?", True, interactive)
    return ch


def cmd_integrate(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--dry-run": "bool", "--yes": "bool",
        "--bundle": "str", "--file": "str",
    })
    if opts["help"]:
        print("swissknifeman integrate [--target P] [--bundle minimal|recommended|full|custom] "
              "[--yes] [--dry-run] [--file settings.json|settings.local.json]")
        return
    target, _ = resolve_target(env, opts, allow_home_confirm=True)
    if target == env.root.resolve():
        die("это сам реестр swissknifeman — запусти integrate из потребляющего проекта")
    load_config(env, target)  # ранняя валидация .swissknife.json

    dry = opts["dry_run"]
    auto = opts["yes"] or not sys.stdin.isatty()
    bundle = opts["bundle"] or ("recommended" if auto else "custom")
    if bundle not in tuple(BUNDLES) + ("custom",):
        die(f"неизвестный bundle: {bundle} (minimal|recommended|full|custom)")
    interactive = sys.stdin.isatty() and not opts["yes"]

    print(f"=== swissknifeman integrate → {target} ===")
    print(f"Бандл: {bundle}" + ("  (dry-run — ничего не пишу)" if dry else ""))
    choices = _gather(env, target, opts, bundle, interactive)

    _block_prereqs(env, dry, interactive)
    _block_skills(env, target, choices, dry)
    _block_perms(env, target, choices, dry)
    _block_autoapprove(target, choices, dry)
    _block_memory(env, target, choices, dry)
    _block_hub(env, target, choices, dry)
    _block_brain(target, choices)

    print("\n=== Готово ===" + (" (dry-run)" if dry else ""))
    print("Перезапусти сессию Claude Code в проекте, чтобы хуки/плагины подхватились.")
