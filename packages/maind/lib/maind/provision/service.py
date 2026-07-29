"""maind service — управление демоном памяти через systemd --user.

Юнит живёт в ~/.config/systemd/user/maind-memory.service (без root): автостарт при
логине, авто-рестарт при краше и консольное управление
`maind service start|stop|restart|status|logs`. ExecStart запускает демон в переднем
плане (`maind memory run` → exec node), поэтому systemd трекает его как MAINPID.

По образцу Brain (lib/brain/service.py)."""
import getpass
import shutil
import subprocess

from ..common import die
from ..config import load_config
from ..memory import refuse_if_client_role

UNIT = "maind-memory.service"
SERVICE_SUBCMDS = {"install", "uninstall", "start", "stop", "restart",
                   "status", "logs", "enable", "disable"}


def _unit_path(env):
    return env.home / ".config" / "systemd" / "user" / UNIT


def _unit_text(env):
    """Содержимое .service. Абсолютные пути из Env (юнит привязан к этой установке)."""
    exec_start = env.root / "bin" / "maind"
    doc = env.root / "docs" / "guide" / "systemd.md"
    return f"""[Unit]
Description=mAInd — демон общей памяти экосистемы (agent-memory)
Documentation=file://{doc}
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory={env.root}
ExecStart={exec_start} memory run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def _ensure_systemd():
    if shutil.which("systemctl") is None:
        die("systemctl не найден — это не systemd-система; "
            "поднимайте память вручную: maind start --only memory")
    r = subprocess.run(["systemctl", "--user", "is-system-running"],
                       text=True, capture_output=True)
    # пустой вывод при ненулевом коде = нет user-инстанса (голый SSH без linger)
    if r.returncode != 0 and not (r.stdout or "").strip():
        die("нет user-сессии systemd. По SSH: войдите в графическую сессию "
            "или выполните `loginctl enable-linger " + getpass.getuser() + "`")


def _sc(*args):
    return subprocess.run(["systemctl", "--user", *args])


def cmd_service(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind service <install|uninstall|start|stop|restart|status|logs|"
              "enable|disable>")
        return
    sub, rest = argv[0], argv[1:]
    _ensure_systemd()
    path = _unit_path(env)

    if sub == "install":
        config, _source = load_config(env)
        refuse_if_client_role(config)   # client не поднимает локальный демон (ADR-0001, D27)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_unit_text(env), encoding="utf-8")
        _sc("daemon-reload")
        r = _sc("enable", "--now", UNIT)
        if r.returncode != 0:
            die("не удалось enable --now (см. вывод выше)")
        print(f"\nУстановлен и запущен: {path}")
        print("Автостарт при логине включён.")
        print("Старт без логина (при загрузке ОС, опц.):")
        print(f"  loginctl enable-linger {getpass.getuser()}")
        print("Управление: maind service {start|stop|restart|status|logs}")
        return

    if sub == "uninstall":
        _sc("disable", "--now", UNIT)
        if path.exists():
            path.unlink()
        _sc("daemon-reload")
        print(f"maind-memory удалён из systemd --user ({path} снят)")
        return

    if sub == "logs":
        args = rest if rest else ["-n", "100", "-f"]
        subprocess.run(["journalctl", "--user", "-u", UNIT, *args])
        return

    if sub in ("start", "stop", "restart", "status", "enable", "disable"):
        if not path.exists():
            die("юнит не установлен — сначала: maind service install")
        r = _sc(sub, UNIT)
        # status у остановленного юнита возвращает 3 — это не ошибка
        if r.returncode != 0 and sub != "status":
            die(f"systemctl --user {sub} вернул {r.returncode}")
        return

    die(f"неизвестная сервис-команда: {sub} ({'|'.join(sorted(SERVICE_SUBCMDS))})")
