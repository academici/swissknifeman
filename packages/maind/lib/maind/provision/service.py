"""Manage the memory daemon through systemd --user.

The rootless user unit starts on login, restarts after failure, and tracks the
foreground `maind memory run` process as MAINPID.
"""
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
    """Render .service content with absolute paths for this installation."""
    exec_start = env.root / "bin" / "maind"
    doc = env.root / "docs" / "guide" / "systemd.md"
    return f"""[Unit]
Description=mAInd — ecosystem shared memory daemon (agent-memory)
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
        die("systemctl not found - this is not systemd-system; "
            "raise memory manually: maind start --only memory")
    r = subprocess.run(["systemctl", "--user", "is-system-running"],
                       text=True, capture_output=True)
    # Empty nonzero output means no user instance (for example bare SSH without linger).
    if r.returncode != 0 and not (r.stdout or "").strip():
        die("no user-sessions systemd. By SSH: log into the graphics session "
            "or run `loginctl enable-linger " + getpass.getuser() + "`")


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
        refuse_if_client_role(config)   # A client role must not start a local daemon.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_unit_text(env), encoding="utf-8")
        _sc("daemon-reload")
        r = _sc("enable", "--now", UNIT)
        if r.returncode != 0:
            die("failed enable --now (see output above)")
        print(f"\nInstalled and running: {path}")
        print("Autostart upon login is enabled.")
        print("Start without login (when loading OS, opt.):")
        print(f"  loginctl enable-linger {getpass.getuser()}")
        print("Control: maind service {start|stop|restart|status|logs}")
        return

    if sub == "uninstall":
        _sc("disable", "--now", UNIT)
        if path.exists():
            path.unlink()
        _sc("daemon-reload")
        print(f"maind-memory removed from systemd --user ({path} removed)")
        return

    if sub == "logs":
        args = rest if rest else ["-n", "100", "-f"]
        subprocess.run(["journalctl", "--user", "-u", UNIT, *args])
        return

    if sub in ("start", "stop", "restart", "status", "enable", "disable"):
        if not path.exists():
            die("unit not installed - first: maind service install")
        r = _sc(sub, UNIT)
        # A stopped unit returns 3 for status; that is not an error.
        if r.returncode != 0 and sub != "status":
            die(f"systemctl --user {sub} returned {r.returncode}")
        return

    die(f"unknown service command: {sub} ({'|'.join(sorted(SERVICE_SUBCMDS))})")
