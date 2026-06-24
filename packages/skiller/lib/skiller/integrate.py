"""integrate — визард интеграции swissknifeman в проект.

Проходит чеклист «выбери, что хочешь из максимального функционала» и применяет
выбранное, переиспользуя существующие команды: do_connect/do_vendor (скиллы),
generate_hub (хаб). Окружение Claude Code (permissions/MCP/auto-approve/memory)
вынесено в отдельный пакет `harness` — соответствующие блоки делегируются ему через
subprocess (как maind делегирует skiller). Безопасно: --dry-run, merge-only, confirm.

Блоки: пререквизиты → скиллы → permissions → MCP → auto-approve → memory → hub → brain.
Скилл-блоки (skills/hub) — здесь; окружение (permissions/MCP/auto-approve/memory) — в harness.
"""
import subprocess
import sys

from .common import apply_permissions, die, harness_bin, parse_flags, warn
from .config import (autodetect, load_config, load_profile, resolve_profile_name,
                     resolve_target)
from .connect import do_connect
from .vendor import do_vendor
from .hub import generate_hub
from .topology import cmd_topology

# Бандл = пред-ответы на чеклист. custom → спрашиваем интерактивно.
# mcp=True → раздать dev-дефолтные MCP-серверы (резолв по autodetect в _gather).
BUNDLES = {
    "minimal":     {"skills": "connect", "perms": False, "mcp": False,
                    "autoapprove": None, "memory": None, "hub": False, "brain": False},
    "recommended": {"skills": "connect", "perms": True, "mcp": True,
                    "autoapprove": "strict", "memory": None, "hub": True, "brain": False},
    "full":        {"skills": "connect", "perms": True, "mcp": True,
                    "autoapprove": "strict", "memory": "federation", "hub": True, "brain": True},
}
AA_MODES = ("strict", "permissive", "bypass", "off")
MEM_MODES = ("file", "federation", "agentmemory", "off")
# MCP-серверы, раздаваемые в среды разработки по умолчанию (пресеты — в пакете harness).
DEV_MCP = ("context7",)


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


# --- harness delegation (окружение Claude Code вынесено в пакет harness) -------
def _run_harness(env, args):
    """Выполнить команду пакета harness (настройка окружения). False — если harness
    не установлен (тогда блок мягко пропускается, как раньше при отсутствии скрипта)."""
    binp = harness_bin(env)
    if binp is None:
        warn("  harness не установлен — пропуск (packages/harness/install.sh)")
        return False
    sys.stdout.flush()
    r = subprocess.run([str(binp)] + args, check=False)
    if r.returncode != 0:
        # graceful: визард не валим, но НЕ молчим — иначе «готово» при непримен. блоке
        warn(f"  harness вернул код {r.returncode} — блок мог не примениться "
             f"({args[0] if args else ''})")
    return True


# --- choices helpers (политика выбора — на стороне визарда) --------------------
def _default_mcp(target):
    """MCP-серверы по умолчанию для среды разработки (не для obsidian-vault)."""
    return list(DEV_MCP) if autodetect(target) != "obsidian-vault" else []


def _available_mcp(env):
    """Имена доступных MCP-пресетов — через `harness mcp --list` (пусто, если harness нет)."""
    binp = harness_bin(env)
    if binp is None:
        return []
    try:
        out = subprocess.run([str(binp), "mcp", "--list"],
                             capture_output=True, text=True, check=False).stdout
    except OSError:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _parse_mcp_flag(opts):
    """--mcp a,b,c → ['a','b','c'] (trim, без пустых)."""
    raw = opts.get("mcp")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []


def _add_unique(lst, names):
    """Дописать names в lst, сохраняя порядок и без дублей. Возвращает lst."""
    for name in names:
        if name and name not in lst:
            lst.append(name)
    return lst


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
        print("  ✗ файлы хуков не установлены — нужно: harness hooks --global")
        if not dry and interactive and \
                _yn("  Установить файлы хуков глобально сейчас?", False):
            _run_harness(env, ["hooks", "--global"])


def _block_skills(env, target, choices, dry):
    ch = choices["skills"]
    print(f"\n[1] Скиллы: {ch or 'пропуск'}")
    if not ch:
        return
    opts = {"dry_run": dry, "hub": choices["hub"],
            "profile": choices.get("profile") or ""}
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
    apply_permissions(env, target, choices.get("perms_presets", ""), dry)


def _block_mcp(env, target, choices, dry):
    """Делегировать установку MCP-серверов пакету harness (merge-only в .mcp.json)."""
    servers = choices.get("mcp") or []
    print(f"\n[3] MCP-серверы: {', '.join(servers) if servers else 'пропуск'}")
    if not servers:
        return
    args = ["mcp", "--target", str(target), "--mcp", ",".join(servers)]
    if dry:
        args.append("--dry-run")
    _run_harness(env, args)


def _block_autoapprove(env, target, choices, dry):
    mode = choices["autoapprove"]
    print(f"\n[4] auto-approve: {mode or 'пропуск'}")
    if not mode:
        return
    args = ["hooks", "--target", str(target), "--auto-approve", mode,
            "--file", choices["settings_file"]]
    if dry:
        args.append("--dry-run")
    _run_harness(env, args)


def _block_memory(env, target, choices, dry):
    brain_mode = choices["memory"]
    print(f"\n[5] memory: {('brain=' + choices.get('memory_brain', 'core') + ' mode=' + brain_mode) if brain_mode else 'пропуск'}")
    if not brain_mode:
        return
    brain = choices.get("memory_brain") or "core"
    args = ["hooks", "--target", str(target), "--memory", f"{brain}:{brain_mode}"]
    if dry:
        args.append("--dry-run")
    _run_harness(env, args)


def _block_hub(env, target, choices, dry):
    # Хаб уже сгенерён внутри connect/vendor, если skills+hub. Иначе — отдельно.
    if not choices["hub"] or choices["skills"]:
        return
    print("\n[6] Hub")
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
    print("\n[7] Brain docs-sync (подсказка — настраивается со стороны волта)")
    print("  В заметке проекта в Brain-волте добавь во frontmatter:")
    print(f"      repo: {target}")
    print("  Затем: brain status <project> / brain sync <project>")


# --- choices assembly ---------------------------------------------------------
def _profile_dict(env, target, opts):
    """Полный профиль проекта (по иерархии flag>config>autodetect) или {} — если
    выбор задан явными buckets/профиль не резолвится."""
    config = load_config(env, target)
    name = resolve_profile_name(target, config, opts.get("profile") or "")
    if not name:
        return "", {}
    try:
        return name, load_profile(env, name)
    except SystemExit:
        return name, {}


def _apply_profile_env(base, profile):
    """Влить профильное СОДЕРЖИМОЕ окружения в choices: harness_presets/mcp/hooks.
    Бандл задаёт тумблеры (вкл/выкл), профиль наполняет значениями для типа."""
    presets = profile.get("harness_presets")
    if presets:
        base["perms_presets"] = ",".join(presets)
    base["mcp"] = _add_unique(list(profile.get("mcp") or []), base.get("mcp") or [])
    hooks = profile.get("hooks") or {}
    if "auto_approve" in hooks:
        aa = hooks["auto_approve"]
        base["autoapprove"] = None if aa in (None, "off") else aa
    if "memory" in hooks:
        mem = hooks["memory"]
        base["memory"] = None if mem in (None, "off") else mem


def _gather(env, target, opts, bundle, interactive):
    base = dict(BUNDLES.get(bundle, BUNDLES["recommended"]))
    base["settings_file"] = opts.get("file") or "settings.json"
    base["memory_brain"] = "core"
    prof_name, profile = _profile_dict(env, target, opts)
    base["profile"] = prof_name
    if bundle != "custom":
        # авто-пресеты permissions (autodetect внутри harness при пустом)
        base["perms_presets"] = ""
        # mcp=True в бандле → dev-дефолты (context7), но не для obsidian-vault;
        # --mcp <a,b> добавляет opt-in пресеты поверх (явный выбор бьёт dev-гейт)
        base["mcp"] = _add_unique(
            _default_mcp(target) if base.get("mcp") else [], _parse_mcp_flag(opts))
        # профиль (если есть) наполняет presets/mcp/hooks содержимым под тип
        _apply_profile_env(base, profile)
        return base

    # custom — интерактивный чеклист
    detected = autodetect(target)
    print(f"Проект: {target}  (autodetect: {detected})")
    ch = {"settings_file": opts.get("file") or "settings.json",
          "memory_brain": "core", "profile": prof_name}
    ch["skills"] = _ask_choice("Канал скиллов", ("connect", "vendor", "skip"),
                               "connect", interactive)
    if ch["skills"] == "skip":
        ch["skills"] = None
    if ch["skills"] == "vendor":
        ch["skills_agent"] = _ask_choice("  агент", ("cursor", "generic", "claude"),
                                         "cursor", interactive)
    ch["perms"] = _ask_yn("Применить permissions-пресеты (autodetect)?", True, interactive)
    ch["perms_presets"] = ""
    if detected != "obsidian-vault":
        want_mcp = _ask_yn(
            "Установить MCP context7 (up-to-date docs библиотек)?", True, interactive)
        ch["mcp"] = list(DEV_MCP) if want_mcp else []
    else:
        ch["mcp"] = []
    # доп. opt-in пресеты: интерактивный ввод + флаг --mcp
    extra_avail = [m for m in _available_mcp(env) if m not in ch["mcp"]]
    if interactive and extra_avail:
        picked = _ask_text(
            f"  доп. MCP-пресеты через запятую ({', '.join(extra_avail)}); Enter — пропуск",
            "", interactive)
        _add_unique(ch["mcp"], (s.strip() for s in picked.split(",")))
    _add_unique(ch["mcp"], _parse_mcp_flag(opts))
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
        "--bundle": "str", "--file": "str", "--mcp": "str", "--profile": "str",
    })
    if opts["help"]:
        print("skiller integrate [--target P] [--bundle minimal|recommended|full|custom] "
              "[--profile name] [--yes] [--dry-run] "
              "[--file settings.json|settings.local.json] [--mcp name1,name2]")
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

    print(f"=== skiller integrate → {target} ===")
    print(f"Бандл: {bundle}" + ("  (dry-run — ничего не пишу)" if dry else ""))
    choices = _gather(env, target, opts, bundle, interactive)

    _block_prereqs(env, dry, interactive)
    _block_skills(env, target, choices, dry)
    _block_perms(env, target, choices, dry)
    _block_mcp(env, target, choices, dry)
    _block_autoapprove(env, target, choices, dry)
    _block_memory(env, target, choices, dry)
    _block_hub(env, target, choices, dry)
    _block_brain(target, choices)

    print("\n=== Готово ===" + (" (dry-run)" if dry else ""))
    print("Перезапусти сессию Claude Code в проекте, чтобы хуки/плагины подхватились.")
