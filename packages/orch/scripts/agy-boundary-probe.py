#!/usr/bin/env python3
"""Probe local guard limitations with synthetic files/listeners, without AGY or credentials.

This diagnostic never authorizes a provider. Exit zero means the probes ran, not
that isolation is sufficient. All resources belong to a private temporary directory.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile


CANARY = r'''
import json, pathlib, socket, sys
observed = {}
for name, action in (
    ("outside_write", lambda: pathlib.Path(sys.argv[1]).write_text("synthetic")),
    ("host_read", lambda: pathlib.Path(sys.argv[2]).read_text()),
    ("tcp", lambda: socket.create_connection(("127.0.0.1", int(sys.argv[3])), timeout=1)),
    ("daemon_socket", lambda: socket.socket(socket.AF_UNIX).connect(sys.argv[4])),
):
    try:
        action()
        observed[name] = "allowed"
    except OSError as exc:
        observed[name] = f"denied:{exc.errno}"
print(json.dumps(observed))
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agy-boundary-") as directory:
        root = Path(directory)
        work = root / "work"
        work.mkdir()
        secret = root / "synthetic-host-secret"
        secret.write_text("synthetic")
        with socket.socket() as tcp, socket.socket(socket.AF_UNIX) as daemon:
            tcp.bind(("127.0.0.1", 0))
            tcp.listen()
            daemon.bind(str(root / "daemon.sock"))
            daemon.listen()
            command = ["python3", "-c", CANARY, str(root / "outside"), str(secret),
                       str(tcp.getsockname()[1]), str(root / "daemon.sock")]
            guard = ["python3", str(Path(__file__).with_name("ro-run.py")), "--no-default-rw",
                     "--rw", str(work), "--rw", "/dev", "--"]
            # Exercise inheritance into a grandchild, not just the guard's direct exec.
            child = ["python3", "-c", "import subprocess,sys;sys.exit(subprocess.call(sys.argv[1:]))"]
            probes = {"landlock_descendant": guard + child + command}
            if shutil.which("bwrap"):
                probes["bwrap_network_namespace"] = ["bwrap", "--unshare-user", "--unshare-net",
                                                       "--ro-bind", "/", "/", "--"] + command
            results = {}
            for name, argv in probes.items():
                run = subprocess.run(argv, capture_output=True, text=True, timeout=10)
                results[name] = {"exit": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
            print(json.dumps({"admission": "unproven", "probes": results}, indent=2))


if __name__ == "__main__":
    main()
