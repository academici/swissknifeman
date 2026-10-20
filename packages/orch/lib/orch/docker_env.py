"""Optional check of the Docker environment of the machine (``orch.docker*`` rows of ``orch doctor``).

Docker is not required by orch. When it is installed, the acceptance checks of a piece of work usually run in containers,
started by the conductor under the user that runs it; this module says how that daemon is reached and how far its
authority goes. ``collect`` reads the machine (the ``docker`` CLI, the socket, the credential configuration); ``assess``
turns those facts into ``check-result/v1`` rows and changes nothing.
"""
from __future__ import annotations

import grp
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

SCHEMA = "urn:swissknifeman:aicore:check-result:v1"
ROOTFUL_SOCKETS = ("/var/run/docker.sock", "/run/docker.sock")
DOC = "packages/orch/docs/docker-environment.md"


def _run(argv: list, timeout: int = 15):
    """``(exit, stdout, stderr)``; ``(None, "", reason)`` when the command cannot be started or is too slow."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return None, "", str(error)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def _socket_facts(path: str, uid: int, gids: set) -> dict:
    try:
        info = os.stat(path)
    except OSError:
        return {"path": path, "exists": False}
    try:
        group = grp.getgrgid(info.st_gid).gr_name
    except KeyError:
        group = str(info.st_gid)
    return {"path": path, "exists": True, "is_socket": stat.S_ISSOCK(info.st_mode), "owner_uid": info.st_uid,
            "group": group, "group_gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
            "user_in_group": info.st_gid in gids, "owned_by_user": info.st_uid == uid}


def _endpoint(env: dict) -> str | None:
    if env.get("DOCKER_HOST"):
        return env["DOCKER_HOST"]
    code, out, _ = _run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], 10)
    return out if code == 0 and out else None


def _credential_helpers(home: Path) -> dict:
    """``{"store": name|None, "helpers": {name: found}}`` from ``~/.docker/config.json``."""
    try:
        config = json.loads((home / ".docker" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"store": None, "helpers": {}}
    names = {config.get("credsStore")} | set((config.get("credHelpers") or {}).values())
    names.discard(None)
    return {"store": config.get("credsStore"),
            "helpers": {name: shutil.which(f"docker-credential-{name}") is not None for name in sorted(names)}}


def collect(env: dict | None = None, home: Path | None = None) -> dict:
    """The facts about Docker on this machine; ``installed`` false when the CLI is missing."""
    env = dict(os.environ if env is None else env)
    facts = {"installed": shutil.which("docker") is not None}
    if not facts["installed"]:
        return facts
    endpoint = _endpoint(env)
    facts["endpoint"] = endpoint
    code, out, err = _run(["docker", "info", "--format", "{{json .SecurityOptions}}|{{.ServerVersion}}"])
    facts["reachable"] = code == 0
    if code == 0:
        options, _, version = out.rpartition("|")
        try:
            facts["security_options"] = json.loads(options)
        except ValueError:
            facts["security_options"] = []
        facts["server_version"] = version
    else:
        facts["error"] = (err or "docker info failed").splitlines()[-1][:300]
    if endpoint and endpoint.startswith("unix://"):
        facts["socket"] = _socket_facts(endpoint[len("unix://"):], os.getuid(), set(os.getgroups()) | {os.getgid()})
    facts["credentials"] = _credential_helpers(Path(home) if home else Path.home())
    code, out, _ = _run(["docker", "compose", "version", "--short"], 10)
    facts["compose"] = out if code == 0 and out else None
    return facts


def _row(check_id: str, status: str, observed: str, evidence=(), remediation: str | None = None) -> dict:
    doc = {"$schema": SCHEMA, "check_id": check_id, "status": status, "category": "environment", "observed": observed}
    if evidence:
        doc["evidence"] = list(evidence)
    if remediation:
        doc["remediation"] = remediation
    return doc


def assess(facts: dict) -> list:
    """The rows for ``facts``: ``orch.docker`` (the daemon and how far its authority goes), ``orch.docker-credentials``
    and ``orch.docker-compose``. Docker is optional: without the CLI every row is ``skip``."""
    if not facts.get("installed"):
        return [_row("orch.docker", "skip", "docker is not installed (optional: orch needs it only when the checks of a "
                                            "piece of work run in containers)")]
    rows = [_daemon_row(facts)]
    if facts.get("reachable"):
        rows.append(_credentials_row(facts["credentials"]))
        rows.append(_row("orch.docker-compose", "ok", f"docker compose {facts['compose']}", ) if facts.get("compose")
                    else _row("orch.docker-compose", "warn", "the docker compose plugin does not answer",
                              remediation="install the docker-compose-plugin package of Docker"))
    return rows


def _daemon_row(facts: dict) -> dict:
    sock = facts.get("socket") or {}
    evidence = [f"endpoint: {facts.get('endpoint') or '-'}"]
    if sock.get("exists"):
        evidence.append(f"socket: owner uid {sock['owner_uid']}, group {sock['group']}, mode {sock['mode']:o}")
    if not facts.get("reachable"):
        denied = "permission denied" in facts.get("error", "").lower()
        return _row("orch.docker", "warn",
                    "docker is installed, but the daemon cannot be used by this user: " + facts.get("error", ""),
                    evidence, remediation=(
                        "the user has no access to the socket: for a rootless daemon see " + DOC
                        if denied else "start the daemon (`systemctl start docker`, or `systemctl --user start docker` "
                                       "for rootless) and check DOCKER_HOST and `docker context ls`; see " + DOC))
    evidence.append(f"server: {facts.get('server_version', '-')}")
    if "name=rootless" in facts.get("security_options", []):
        who = "the daemon is rootless" + (" and its socket belongs to this user" if sock.get("owned_by_user") else "")
        if sock.get("owned_by_user"):
            return _row("orch.docker", "ok", who + ": containers have the authority of this user, not of root; for an "
                        "agent that runs checks keep it apart from your personal files by using a dedicated account",
                        evidence)
        return _row("orch.docker", "ok", who + ": containers have no root authority on the host", evidence)
    if sock.get("exists") and sock.get("owner_uid") == 0 and sock.get("user_in_group"):
        return _row("orch.docker", "warn",
                    f"the daemon is rootful and this user reaches it through the group {sock['group']}: whoever controls "
                    "it controls the host as root (a container may mount `/`). Everything the conductor runs in "
                    "containers (checks, tests, compose files of the work) has that authority",
                    evidence + ["the sandbox of the executor cannot reach this socket (by design)"],
                    remediation="acceptable on a single-user development machine; the recommended practice is a rootless "
                                f"daemon, ideally under a dedicated account (see {DOC})")
    return _row("orch.docker", "ok", "the daemon is reachable and is not shared through a group of this user", evidence)


def _credentials_row(credentials: dict) -> dict:
    missing = [name for name, found in credentials["helpers"].items() if not found]
    if missing:
        return _row("orch.docker-credentials", "fail",
                    "the Docker credential helper named in ~/.docker/config.json is not installed: "
                    + ", ".join(f"docker-credential-{name}" for name in missing) + "; every image pull and build fails",
                    remediation="install the helper, or remove the credsStore/credHelpers entry of ~/.docker/config.json "
                                "(a change to your own file, made by you)")
    helpers = ", ".join(credentials["helpers"]) or "none configured"
    return _row("orch.docker-credentials", "ok", f"credential helpers: {helpers}")


def check() -> list:
    return assess(collect())
