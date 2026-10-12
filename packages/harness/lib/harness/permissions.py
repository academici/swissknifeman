"""Internal documentation."""
import subprocess
import sys

from aicore.util.cli import parse_flags
from aicore.util.term import die, warn


def apply_permissions(env, target, presets="", dry_run=False, settings_file=None):
    """Internal documentation."""
    script = env.apply_script
    if not script.exists():
        warn("scripts/apply-permissions.sh not found - skip permissions")
        return False
    cmd = ["bash", str(script), "--target", str(target)]
    if presets:
        cmd += ["--preset", presets]
    if settings_file:
        cmd += ["--file", settings_file]
    if dry_run:
        cmd.append("--dry-run")
    sys.stdout.flush()
    subprocess.run(cmd, check=False)
    return True


def cmd_permissions(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--preset": "str", "--file": "str",
        "--dry-run": "bool", "--list": "bool", "--global": "bool",
    })
    if opts["help"]:
        print("harness permissions [--target P] [--preset a,b,...] "
              "[--file settings.json|settings.local.json] [--dry-run] "
              "[--list] [--global]")
        return
    script = env.apply_script
    if not script.exists():
        die(f"not found {script} — package harness damaged")
    cmd = ["bash", str(script)]
    if opts["list"]:
        cmd.append("--list")
    elif opts["global"]:
        cmd.append("--global")
        if opts["dry_run"]:
            cmd.append("--dry-run")
    else:
        if not opts["target"]:
            die("needed --target P (or --list / --global)")
        cmd += ["--target", opts["target"]]
        if opts["preset"]:
            cmd += ["--preset", opts["preset"]]
        if opts["file"]:
            cmd += ["--file", opts["file"]]
        if opts["dry_run"]:
            cmd.append("--dry-run")
    sys.stdout.flush()
    rc = subprocess.run(cmd, check=False).returncode
    if rc:
        sys.exit(rc)
