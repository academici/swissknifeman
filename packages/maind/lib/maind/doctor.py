"""doctor — диагностика окружения узла maind."""
import json
import os
import shutil
import sys
from pathlib import Path

from .common import parse_args
from .memory import auth_headers, check_auth, health, resolve_ports, resolve_secret


def provider_trust_report(env, config):
    """Read-only provider trust aggregate for enabled projects."""
    from .provision.sync import contexts
    from .provision.workspace import norm_path, provider_trust, trusted_dirs
    trusted = trusted_dirs(env)
    rows = []
    for context in contexts(env, config, [p for p in config.get("projects") or []
                                           if p.get("enabled", True)]):
        path = context.get("local_path")
        rows.extend({"project_id": context.id, **row} for row in provider_trust(
            context, trusted=bool(path and norm_path(path) in trusted)))
    return rows


def _skill_drift(env, config):
    """Дрейф managed-скиллов maind (ecosystem-mcp/ecosystem-setup) по флоту enabled-
    проектов: сухой прогон обоих провиженеров (mode=auto, dry=True) — state != 'fresh'
    значит скилл отсутствует ИЛИ шаблон в maind с тех пор обновился (устарел). Ничего
    не пишет; реальная раскатка — `maind sync --only ecosystem-skill,setup-skill`."""
    from .federation import _enabled_projects
    from .provision.skilldoc import apply_ecosystem_skill, apply_setup_skill
    drifted = []
    for p in _enabled_projects(config):
        local = p.get("local_path")
        if not local or not Path(os.path.expanduser(local)).is_dir():
            continue
        for fn, label in ((apply_ecosystem_skill, "ecosystem-mcp"),
                          (apply_setup_skill, "ecosystem-setup")):
            try:
                res = fn(env, config, p, "auto", True)
            except Exception:
                continue
            if res.get("state") not in {"fresh", "foreign-owner"}:
                drifted.append((p.get("id"), label, res["state"]))
    return drifted


def _skill_drift_report(env, config, detail):
    """detail=False: одна summary-строка для дефолтного doctor. detail=True: по-проектная
    разбивка (--skill-drift)."""
    drifted = _skill_drift(env, config)
    if not detail:
        if drifted:
            projects = sorted({pid for pid, _, _ in drifted})
            print(f"  [warn] managed-скиллы (ecosystem-mcp/setup): {len(projects)} "
                  "проект(ов) отстали от шаблона (детали: maind doctor --skill-drift)")
        else:
            print("  [ok ] managed-скиллы (ecosystem-mcp/setup): дрейфа от шаблона нет")
        return
    print("\nДрейф managed-скиллов maind (ecosystem-mcp/ecosystem-setup, сухой расчёт):")
    if not drifted:
        print("  (все enabled-проекты синхронизированы с текущими шаблонами)")
        return
    by_project = {}
    for pid, label, state in drifted:
        by_project.setdefault(pid, []).append(f"{label}:{state}")
    for pid, items in sorted(by_project.items()):
        print(f"  [warn] {pid}: " + ", ".join(items)
              + "  (применить: maind sync --project " + pid + " --only ecosystem-skill,setup-skill)")


def _channel_overlap(env, config):
    """Дубль-канал skiller (бакет раздаётся ОДНОВРЕМЕННО plugin'ом (connect) и
    вендором) по флоту enabled-проектов: сухой `skiller status --json` на каждый —
    детект живёт в skiller (`channel_overlap`), doctor только агрегирует по флоту
    (field-feedback: найдено вручную на agelto/azguard/dterema — теперь на радаре
    само). Возвращает [(project_id, [bucket, …])]."""
    import json
    import subprocess

    from .federation import _enabled_projects
    from .provision.orchestrate import _sibling_bin
    try:
        skm_bin = _sibling_bin(config, "swissknifeman")
    except SystemExit:
        return []
    overlaps = []
    for p in _enabled_projects(config):
        local = p.get("local_path")
        if not local or not Path(os.path.expanduser(local)).is_dir():
            continue
        try:
            r = subprocess.run([str(skm_bin), "status", "--target", local, "--json"],
                               capture_output=True, text=True, timeout=15, check=False)
            data = json.loads(r.stdout)
        except (subprocess.SubprocessError, ValueError, OSError):
            continue
        overlap = data.get("channel_overlap") or []
        if overlap:
            overlaps.append((p.get("id"), overlap))
    return overlaps


def _channel_hygiene_report(env, config, detail):
    """detail=False: одна summary-строка. detail=True (--channel-drift): по-проектная
    разбивка дублей канала."""
    overlaps = _channel_overlap(env, config)
    if not detail:
        if overlaps:
            print(f"  [warn] дубль-канал skiller (connect+vendor): {len(overlaps)} "
                  "проект(ов) раздают скиллы дважды (детали: maind doctor --channel-drift)")
        else:
            print("  [ok ] дубль-канал skiller (connect+vendor): не найден")
        return
    print("\nДубль-канал skiller (бакет ОДНОВРЕМЕННО plugin+vendor, сухой запрос):")
    if not overlaps:
        print("  (не найден ни в одном enabled-проекте)")
        return
    for pid, buckets in overlaps:
        print(f"  [warn] {pid}: {' '.join(buckets)}  (почистить: skiller connect "
              "--target <path> --cleanup-vendored — плюс отдельно вручную, если "
              "вендор через .swissknifeman/config.json, не legacy .swissknife.json)")


def _gitignore_drift(config, only=None):
    """Сверка каждого enabled-проекта с картой `configs/gitignore-policy.json` (read-only):
    что должно быть в .gitignore, а что коммититься. Возвращает [(project_id, findings)]."""
    from core.gitignore_policy import PolicyError, check_project, load_policy

    from .federation import _enabled_projects
    policy = load_policy()
    rows = []
    for p in _enabled_projects(config):
        if only and p.get("id") != only:
            continue
        local = p.get("local_path")
        path = Path(os.path.expanduser(local)) if local else None
        if not path or not path.is_dir():
            continue
        try:
            rows.append((p.get("id"), check_project(path, policy), policy))
        except PolicyError:
            continue
    return rows


def _gitignore_drift_report(config, detail, *, only=None, as_json=False, block=False):
    """detail=False: одна summary-строка для дефолтного doctor. detail=True
    (--gitignore-drift): по-проектная разбивка, --json, --block (готовые строки .gitignore)."""
    from core.gitignore_policy import PolicyError, recommended_block
    try:
        rows = _gitignore_drift(config, only)
    except PolicyError as exc:
        print(f"  [warn] карта gitignore недоступна: {exc}")
        return
    errors = {pid: [f for f in found if f["level"] == "error"] for pid, found, _ in rows}
    if as_json:
        print(json.dumps({"projects": [{"id": pid, "findings": found} for pid, found, _ in rows]},
                         ensure_ascii=False, indent=2))
        return
    if not detail:
        bad = sorted(pid for pid, errs in errors.items() if errs)
        if bad:
            print(f"  [warn] .gitignore ↔ карта служебных файлов: {len(bad)} проект(ов) расходятся "
                  "(детали: maind doctor --gitignore-drift)")
        else:
            print("  [ok ] .gitignore ↔ карта служебных файлов: расхождений нет")
        return
    print("\nРасхождения .gitignore с картой служебных файлов (configs/gitignore-policy.json):")
    clean = True
    for pid, found, policy in rows:
        problems = [f for f in found if f["level"] != "info"]
        if not problems:
            continue
        clean = False
        print(f"  {pid}: {len([f for f in problems if f['level'] == 'error'])} ошибок, "
              f"{len([f for f in problems if f['level'] == 'warn'])} предупреждений")
        for f in problems:
            print(f"    [{f['level']:<5}] {f['code']}: {f['path']} — {f['fix']}")
        if block:
            lines = recommended_block(found, policy)
            if lines:
                print("    # добавить в .gitignore:")
                for line in lines:
                    print(f"    {line}")
    if clean:
        print("  (расхождений нет ни в одном enabled-проекте)")


def _fleet_context(env, config):
    """Флот-агрегация футпринта первого хода: цикл по registered-проектам → subprocess
    `skiller budget --first-turn --target <path> --json` — токен-математика
    остаётся ЕДИНСТВЕННО в skiller, maind только потребляет готовый JSON (без дубля,
    без кросс-импортов — паттерн doctor --audit settings, D10). Fail-soft: недоступный
    skiller / сломанный вывод / отсутствующий local_path на проект → context='n/a',
    скан флота продолжается."""
    import json
    import subprocess

    from .federation import _enabled_projects
    from .provision.orchestrate import _sibling_bin
    try:
        skm_bin = _sibling_bin(config, "swissknifeman")
    except SystemExit:
        skm_bin = None
    rows = []
    for p in _enabled_projects(config):
        pid = p.get("id")
        local = p.get("local_path")
        path = Path(os.path.expanduser(local)) if local else None
        if not path or not path.is_dir() or skm_bin is None:
            rows.append({"id": pid, "context": "n/a"})
            continue
        try:
            r = subprocess.run(
                [str(skm_bin), "budget", "--first-turn", "--target", str(path), "--json"],
                capture_output=True, text=True, timeout=20, check=False)
            data = json.loads(r.stdout)
            rows.append({"id": pid,
                        "context": {"total": data["total"], "verdict": data["verdict"]}})
        except (subprocess.SubprocessError, ValueError, OSError, KeyError, TypeError):
            rows.append({"id": pid, "context": "n/a"})
    return rows


def _context_report(env, config, as_json):
    import json
    rows = _fleet_context(env, config)
    if as_json:
        print(json.dumps({"projects": rows}, ensure_ascii=False, indent=2))
        return
    print(f"maind doctor --context (футпринт первого хода) — проектов: {len(rows)}")
    if not rows:
        print("  проектов нет — config.json пуст или отсутствует")
        return
    for r in rows:
        ctx = r["context"]
        if ctx == "n/a":
            print(f"  {r['id']:<18} context·n/a")
        else:
            print(f"  {r['id']:<18} context={ctx['total']} {ctx['verdict']}")


def cmd_doctor(env, argv):
    opts, _ = parse_args(argv, {"--quiet": "bool", "--audit": "str", "--json": "bool",
                                "--skill-drift": "bool", "--channel-drift": "bool",
                                "--context": "bool", "--provider-trust": "bool",
                                "--gitignore-drift": "bool", "--project": "str", "--block": "bool"})
    if opts["help"]:
        print("maind doctor [--quiet] — проверка окружения узла\n"
              "maind doctor --audit mcp|claude|deny|core|pao|settings|all [--json] — "
              "fleet-аудит оптимизаций по проектам (read-only)\n"
              "maind doctor --skill-drift — по-проектная разбивка дрейфа "
              "ecosystem-mcp/ecosystem-setup от текущего шаблона\n"
              "maind doctor --channel-drift — по-проектная разбивка дубль-канала "
              "skiller (connect+vendor на один бакет)\n"
              "maind doctor --gitignore-drift [--project ID] [--block] [--json] — сверка "
              ".gitignore/tracking каждого проекта с картой служебных файлов "
              "(configs/gitignore-policy.json; --block печатает строки для .gitignore)\n"
              "maind doctor --context [--json] — флот-агрегация футпринта первого "
              "хода (skiller budget --first-turn по каждому проекту)")
        return

    # --audit: read-only fleet-отчёт о полноте раздачи оптимизаций по проектам
    if opts["audit"]:
        from .analysis.audit import run_audit
        config = {}
        if env.default_config.exists():
            try:
                from .config import load_config
                config, _ = load_config(env)
            except SystemExit:
                config = {}
        run_audit(env, config, opts["audit"], as_json=opts["json"])
        return

    # --context: read-only fleet-агрегация футпринта первого хода (subprocess → skiller)
    if opts["context"]:
        config = {}
        if env.default_config.exists():
            try:
                from .config import load_config
                config, _ = load_config(env)
            except SystemExit:
                config = {}
        _context_report(env, config, as_json=opts["json"])
        return

    if opts["gitignore_drift"]:
        config = {}
        if env.default_config.exists():
            try:
                from .config import load_config
                config, _ = load_config(env)
            except SystemExit:
                config = {}
        _gitignore_drift_report(config, True, only=opts["project"], as_json=opts["json"],
                                block=opts["block"])
        return

    if opts["provider_trust"]:
        from .config import load_config
        config, _src = load_config(env)
        rows = provider_trust_report(env, config)
        if opts["json"]:
            print(json.dumps({"providers": rows, "non_green": sum(not row["green"] for row in rows)}, ensure_ascii=False))
        else:
            print(f"provider trust: non-green={sum(not row['green'] for row in rows)}")
            for row in rows:
                print(f"  {row['project_id']} {row['provider_id']}: " + ("ok" if row["green"] else ", ".join(row["diagnostics"])))
        return

    quiet = opts["quiet"]
    issues = 0

    def check(ok, label, hint=""):
        nonlocal issues
        if not ok:
            issues += 1
        if not quiet or not ok:
            mark = "ok " if ok else "FAIL"
            print(f"  [{mark}] {label}" + (f" — {hint}" if hint and not ok else ""))

    print(f"maind doctor (узел: {env.root})")
    check(sys.version_info >= (3, 8), f"python3 {sys.version.split()[0]}")
    check(shutil.which("node") is not None, "node в PATH",
          "agent-memory — Node-демон; установите Node.js")

    am = env.root / "node_modules" / ".bin" / "agentmemory"
    check(am.exists(), "agentmemory установлен",
          "npm install в корне maind (демон памяти @agentmemory/agentmemory)")
    check(env.memory_config.is_file(), "config/memory/iii-config.yaml на месте",
          "maind migrate from-agentmemory <путь к .agentmemory>")

    try:
        env.state_dir.mkdir(parents=True, exist_ok=True)
        probe = env.state_dir / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    check(writable, f"{env.state_dir} доступен для записи")

    # .maind.json: валидируем через load_config (die ловим, чтобы не прерывать doctor)
    config = None
    if env.default_config.exists():
        try:
            from .config import load_config
            config, source = load_config(env)
            check(True, f"конфиг узла валиден (источник: {source})")
        except SystemExit:
            check(False, "конфиг узла валиден", "см. ошибку валидации выше")
    else:
        legacy = env.root / ".projects.json"
        suffix = (" (есть legacy .projects.json — maind migrate from-brain)"
                  if legacy.exists() else " (создайте из config.example.json)")
        check(True, "config.json отсутствует" + suffix)

    if config:
        _skill_drift_report(env, config, detail=opts.get("skill_drift"))
        _channel_hygiene_report(env, config, detail=opts.get("channel_drift"))
        _gitignore_drift_report(config, False)
        from .codegraph import check_schema_connectivity
        schema_issues = check_schema_connectivity(config)
        check(not schema_issues, "пин Serena/схема .serena/project.yml связны",
              "; ".join(schema_issues))

    # порты памяти — на разрешённых портах (env/конфиг), информативно
    if not quiet:
        http_port, stream_port, url = resolve_ports(env, config)
        up = health(url)
        if not up:
            print(f"  [info] память {url} — не запущена (maind start --only memory)")
        else:
            # /agentmemory/health ВСЕГДА публичен (даже с секретом) — «отвечает» не значит
            # «наши вызовы авторизованы»; различаем явным протектед-пробником (findings §2).
            headers = auth_headers(resolve_secret(env, config)) if config else None
            auth = check_auth(url, headers) if headers else None
            detail = "отвечает, но неавторизован (401) — проверьте memory.secret_file/AGENTMEMORY_SECRET" \
                if auth is False else "отвечает"
            print(f"  [info] память {url} — {detail}")
        print(f"  [info] порты: http :{http_port}, stream :{stream_port} "
              "(override через .env AGENTMEMORY_PORT/STREAM_PORT)")

    print(f"\n{'Все проверки пройдены.' if issues == 0 else f'Проблем: {issues}'}")
    if issues:
        sys.exit(1)
