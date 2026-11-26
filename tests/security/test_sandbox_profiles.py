"""Isolation profiles, coverage proof and permission rendering fail closed (adapters §7).

Offline tests: the container backend runs against a recording fake Docker daemon, so create → persist → start
ordering, recovery by owner labels, cleanup by ID and every pre-spawn refusal are asserted without containers.
A positive container canary needs Docker and a pinned image (``SKM_TEST_CONTAINER_IMAGE``) or loads a local
archive on the host daemon.
"""

import errno
import hashlib
import io
import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import IO, Any, override
from uuid import uuid4

import pytest

from skm.adapters.sandbox.backend import (
    Companion,
    CompanionProof,
    ProofRequest,
    assess,
    request_binding,
    spec_requirements,
)
from skm.adapters.sandbox.container import (
    WORKDIR,
    ContainerSettings,
    CreatedContainer,
    DockerResult,
    container_isolation,
)
from skm.adapters.sandbox.none import none_isolation
from skm.adapters.sandbox.registry import IsolationRegistry, build_isolation_registry
from skm.adapters.sandbox.worktree import worktree_isolation
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.json_types import JsonValue
from skm.modules.policy.application.composition import compose_effective
from skm.modules.policy.domain.paths import PathPolicy, PathRule, PathScope, ScopedPath, unrestricted_policy
from skm.modules.policy.domain.permission_set import PermissionSet
from skm.modules.policy.domain.render import IsolationProperty, isolation_requirements
from skm.modules.runtimes.domain.request import ProcessOwner, ProcessOwnership

IMAGE = "registry.example/skm-cli@sha256:" + "a" * 64
P = IsolationProperty
PROBE_PREFIX = "skm-baseline-"
PROBE_ID_PREFIX = "ba5e110eba5e110e"


# -- fixtures --------------------------------------------------------------------------------------


class Config:
    def __init__(self, values: Mapping[str, JsonValue]) -> None:
        self.values: dict[str, JsonValue] = {
            "policy.default_profile": "workspace-contained",
            "policy.profiles": {},
            "policy.restrictions": [],
            "policy.ceiling.network": "any",
            "policy.ceiling.network_allowlist": [],
            "policy.ceiling.shell": True,
            "policy.ceiling.external_effects": ["git_commit"],
            "policy.ceiling.isolation_profiles": ["none", "worktree", "landlock", "container"],
            "policy.ceiling.commands_denylist": [],
            "policy.approval.required_for": [],
            "policy.access_capabilities.allowed": [],
            "policy.access_capabilities.granted": [],
            "policy.task_authority.operations": [],
            **values,
        }

    def get(self, key: str) -> JsonValue | None:
        return self.values.get(key)


def is_probe(call: Sequence[str]) -> bool:
    """Every call about the baseline probe names it or its container ID."""
    return any(item.startswith((PROBE_PREFIX, PROBE_ID_PREFIX)) for item in call)


def permissions(profile_id: str, **config: JsonValue) -> PermissionSet:
    return compose_effective(
        Config(config), profile_id=profile_id, role_layer=None, task_layer=None, allow_unconfined=True
    )


def make_owner(nonce: str = "n" * 32) -> ProcessOwner:
    return ProcessOwner(
        host_id=uuid4(),
        worker_id=uuid4(),
        attempt_id=uuid4(),
        stage_record_id=uuid4(),
        unit_kind="step",
        unit_id=uuid4(),
        owner_nonce=nonce,
        identity_dir="/run/skm/identity",
    )


class Spec:
    def __init__(self, workdir: Path, **fields: object) -> None:
        self.workdir = workdir
        self.readable: tuple[Path, ...] = ()
        self.writable: tuple[Path, ...] = (workdir,)
        self.protected: tuple[Path, ...] = ()
        self.read_only_root = True
        self.network = "none"
        self.network_hosts: tuple[str, ...] = ()
        self.env: dict[str, str] = {}
        self.materials_dir: Path | None = None
        self.credential_mounts: tuple[dict[str, str], ...] = ()
        self.owner = make_owner()
        vars(self).update(fields)


class FakeDocker:
    """A daemon that records every call; containers are keyed by the ID returned from ``create``. ``inspect``
    answers what Docker stores for the create argv: the image's entrypoint, environment, labels and volumes
    merged in, sizes in bytes, the daemon's defaults filled in, keys left out only where Docker's JSON does.
    A ``VOLUME`` of the image gets an anonymous volume, which ``rm`` leaves behind unless told ``--volumes``,
    and even then a named one or one another container uses stays.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.containers: dict[str, dict[str, Any]] = {}
        self.volumes: dict[str, bool] = {}  # name -> anonymous
        self.daemon: str | None = "daemon-A"
        self.client_dead_after_create = False
        self.env_files: list[tuple[int, str]] = []
        self.security_options = '["name=seccomp,profile=builtin","name=cgroupns"]\n'
        self.info: dict[str, JsonValue] = {
            "DefaultRuntime": "runc",
            "LoggingDriver": "json-file",
            "SwapLimit": True,
            "CgroupVersion": "2",
        }
        self.image_id = "sha256:" + "9" * 64
        self.image_config: dict[str, Any] = {}
        self.masked_paths: list[str] = ["/proc/asound", "/proc/keys"]
        self.readonly_paths: list[str] = ["/proc/bus", "/proc/sys"]

    def verbs(self) -> list[str]:
        return [call[1] for call in self.calls]

    def owner_verbs(self) -> list[str]:
        """The calls about the containers of owners, without those about the baseline probe."""
        return [call[1] for call in self.calls if not is_probe(call)]

    def probe_verbs(self) -> list[str]:
        return [call[1] for call in self.calls if is_probe(call)]

    def _named(self, reference: str) -> str:
        """``docker`` takes a name wherever it takes an ID."""
        for container_id, data in self.containers.items():
            if data.get("record", {}).get("Name") == f"/{reference}":
                return container_id
        return reference

    def _record(self, call: tuple[str, ...], container_id: str, labels: dict[str, str]) -> dict[str, Any]:
        """What ``inspect`` reports for this ``create``; a test changes it to play any other container."""
        values: dict[str, list[str]] = {}
        switches = {"--init", "--read-only", "--interactive", "--privileged"}
        position = call.index("create") + 1
        while call[position].startswith("--"):
            if call[position] in switches:
                values.setdefault(call[position], []).append("")
                position += 1
            else:
                values.setdefault(call[position], []).append(call[position + 1])
                position += 2
        image, cmd = call[position], list(call[position + 1 :])
        config = self.image_config
        env = list(values.get("--env", []))
        for path in values.get("--env-file", []):
            env = [*Path(path).read_text().splitlines(), *env]
        names = {line.partition("=")[0] for line in env}
        for line in config.get("Env", []):
            # merge compares with what it built so far; create without variables takes image's as is
            if not values.get("--env") and not values.get("--env-file"):
                env.append(line)
            elif line.partition("=")[0] not in names:
                names.add(line.partition("=")[0])
                env.append(line)
        mounts: list[dict[str, Any]] = []
        for item in values.get("--mount", []):
            options = {part.partition("=")[0]: part.partition("=")[2] for part in item.split(",")}
            mount = {"Type": options["type"], "Source": options["src"], "Target": options["dst"]}
            mounts.append({**mount, "ReadOnly": True} if "readonly" in options else mount)
        entrypoint = values.get("--entrypoint", config.get("Entrypoint"))
        if entrypoint == [""]:  # the daemon resets it after merging the image, whichever side it came from
            entrypoint = None
        program = [*(entrypoint or []), *cmd]
        memory = (
            int(values["--memory"][0][:-1])
            * {"k": 1024, "m": 1024**2, "g": 1024**3}[values["--memory"][0][-1]]
        )
        # the CLI turns this option into empty paths in the request and never sends the option itself
        unconfined = "systempaths=unconfined" in values["--security-opt"]
        host: dict[str, Any] = {
            "Binds": values.get("--volume"),
            "ContainerIDFile": "",
            "LogConfig": {"Type": self.info["LoggingDriver"], "Config": {}},
            "NetworkMode": values["--network"][0],
            "PortBindings": {},
            "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            "AutoRemove": False,
            "VolumeDriver": "",
            "VolumesFrom": None,
            "ConsoleSize": [0, 0],
            "CapAdd": values.get("--cap-add"),
            "CapDrop": values["--cap-drop"],
            "CgroupnsMode": "host" if self.info["CgroupVersion"] == "1" else "private",
            "Dns": [],
            "DnsOptions": [],
            "DnsSearch": [],
            "ExtraHosts": values.get("--add-host"),
            "GroupAdd": None,
            "IpcMode": values.get("--ipc", ["private"])[0],
            "Cgroup": "",
            "Links": None,
            "OomScoreAdj": 0,
            "PidMode": values.get("--pid", [""])[0],
            "Privileged": "--privileged" in values,
            "PublishAllPorts": False,
            "ReadonlyRootfs": "--read-only" in values,
            "SecurityOpt": [item for item in values["--security-opt"] if item != "systempaths=unconfined"],
            "Tmpfs": dict(item.split(":", 1) for item in values["--tmpfs"]),
            "UTSMode": "",
            "UsernsMode": "",
            "ShmSize": 67108864,
            "Runtime": self.info["DefaultRuntime"],
            "Isolation": "",
            "CpuShares": 0,
            "Memory": memory,
            "NanoCpus": int(float(values["--cpus"][0]) * 10**9),
            "CgroupParent": "",
            "Devices": [],
            "DeviceCgroupRules": None,
            "DeviceRequests": None,
            "MemoryReservation": 0,
            "MemorySwap": memory * 2 if self.info["SwapLimit"] else -1,
            "MemorySwappiness": None,
            "OomKillDisable": None,
            "PidsLimit": int(values["--pids-limit"][0]),
            "Ulimits": [],
            "MaskedPaths": [] if unconfined else list(self.masked_paths),
            "ReadonlyPaths": [] if unconfined else list(self.readonly_paths),
            "Init": "--init" in values,
        }
        if mounts:
            host["Mounts"] = mounts
        return {
            "Id": container_id,
            "Name": "/" + values["--name"][0],
            "Image": self.image_id,
            "Path": program[0],
            "Args": program[1:],
            "Config": {
                "Hostname": container_id[:12],
                "User": values["--user"][0],
                "Tty": False,
                "OpenStdin": "--interactive" in values,
                "Env": env,
                "Cmd": cmd,
                "Image": image,
                "Volumes": config.get("Volumes"),
                "WorkingDir": values["--workdir"][0],
                "Entrypoint": entrypoint,
                "OnBuild": None,
                **({"Healthcheck": config["Healthcheck"]} if "Healthcheck" in config else {}),
            },
            "NetworkSettings": {"Networks": {values["--network"][0]: {"IPAddress": ""}}},
            "HostConfig": host,
        }

    def _inspected(self, data: dict[str, Any]) -> DockerResult:
        if "report" in data:
            return DockerResult(0, data["report"])
        record = json.loads(json.dumps(data.get("record", {})))
        record["State"] = {"Status": data["state"]}
        record.setdefault("Config", {})["Labels"] = data["labels"]
        record["Mounts"] = data.get("mounts", [])
        if "mounts_report" in data:  # one part of the answer says nothing, or something else
            try:
                record["Mounts"] = json.loads(data["mounts_report"])
            except ValueError:
                del record["Mounts"]
        return DockerResult(0, json.dumps([record]))

    def __call__(self, argv: Sequence[str]) -> DockerResult:  # noqa: PLR0911, PLR0912
        call = tuple(argv)
        self.calls.append(call)
        verb, rest = call[1], call[2:]
        if self.daemon is None:
            return DockerResult(1, "", "Cannot connect to the Docker daemon")
        if verb == "info":
            if rest[-1] == "{{json .}}":
                return DockerResult(0, json.dumps({"ID": self.daemon, **self.info}))
            return DockerResult(
                0, self.security_options if "SecurityOptions" in rest[-1] else self.daemon + "\n"
            )
        if verb == "version":
            return DockerResult(0, "27.0.1\n")
        if verb == "image":
            if rest[-1] != IMAGE:
                return DockerResult(1, "", f"Error: No such image: {rest[-1]}")
            return DockerResult(0, json.dumps([{"Id": self.image_id, "Config": self.image_config}]))
        if verb == "create":
            labels = {
                **self.image_config.get("Labels", {}),
                **{
                    key: value
                    for flag, item in itertools.pairwise(call)
                    if flag == "--label"
                    for key, _, value in [item.partition("=")]
                },
            }
            if "--env-file" in call:
                path = Path(call[call.index("--env-file") + 1])
                self.env_files.append((stat.S_IMODE(path.stat().st_mode), path.read_text()))
            digest = hashlib.sha256(f"{len(self.containers)}{labels}".encode()).hexdigest()
            container_id = f"{PROBE_ID_PREFIX}{digest[len(PROBE_ID_PREFIX) :]}" if is_probe(call) else digest
            record = self._record(call, container_id, labels)
            mounts = [
                {
                    "Type": mount["Type"],
                    **({"Name": mount["Source"]} if mount["Type"] == "volume" else {}),
                    "Source": mount["Source"],
                    "Destination": mount["Target"],
                    "RW": not mount.get("ReadOnly", False),
                }
                for mount in record["HostConfig"].get("Mounts", [])
            ]
            for mount in mounts:
                if mount["Type"] == "volume":
                    self.volumes.setdefault(mount["Name"], False)
            mounts += [
                {"Type": "bind", "Source": source, "Destination": target, "RW": not mode}
                for source, target, *mode in (item.split(":") for item in record["HostConfig"]["Binds"] or [])
            ]
            taken = {mount["Destination"] for mount in mounts} | set(record["HostConfig"]["Tmpfs"])
            for declared in self.image_config.get("Volumes") or {}:
                target = os.path.normpath(declared)
                if target in taken:
                    continue
                volume = hashlib.sha256(f"{container_id}{target}".encode()).hexdigest()
                self.volumes[volume] = True
                mounts.append(
                    {
                        "Type": "volume",
                        "Name": volume,
                        "Source": f"/var/lib/docker/volumes/{volume}/_data",
                        "Destination": target,
                        "RW": True,
                    }
                )
            self.containers[container_id] = {
                "labels": labels,
                "state": "created",
                "mounts": mounts,
                "record": record,
            }
            if self.client_dead_after_create and not is_probe(call):
                return DockerResult(137, "", "client killed")
            return DockerResult(0, container_id + "\n")
        if verb == "ps":
            nonce = next(item for item in rest if item.startswith("label=skm.owner_nonce="))
            wanted = nonce.removeprefix("label=skm.owner_nonce=")
            found = [
                cid
                for cid, data in self.containers.items()
                if data["labels"].get("skm.owner_nonce") == wanted
            ]
            return DockerResult(0, "\n".join(found))
        if verb in {"inspect", "stop", "kill", "rm"}:
            container_id = self._named(rest[-1])
            data = self.containers.get(container_id)
            if data is None:
                return DockerResult(1, "", f"Error: No such object: {container_id}")
            if verb == "inspect" and "--type" in rest:
                return self._inspected(data)
            if verb == "inspect" and "{{.State.Status}}" in rest:
                return DockerResult(0, str(data["state"]) + "\n")
            if verb == "inspect":
                return DockerResult(0, "[{}]")
            if verb in {"stop", "kill"}:
                data["state"] = "exited"
            if verb == "rm":
                del self.containers[container_id]
                if "--volumes" in rest:
                    self._release_volumes(data)
            return DockerResult(0, container_id)
        if verb == "volume" and rest[0] == "inspect":
            if rest[-1] not in self.volumes:
                return DockerResult(1, "[]\n", f"Error response from daemon: get {rest[-1]}: no such volume")
            return DockerResult(0, json.dumps([{"Name": rest[-1]}]))
        return DockerResult(1, "", f"unexpected docker call {call}")

    def _release_volumes(self, removed: dict[str, Any]) -> None:
        """``rm --volumes``: an anonymous volume goes unless another container uses it."""
        for mount in removed["mounts"]:
            name = mount.get("Name")
            used = any(
                other.get("Name") == name for data in self.containers.values() for other in data["mounts"]
            )
            if self.volumes.get(name) and not used:
                del self.volumes[name]


def container_backend(
    tmp_path: Path,
    docker: FakeDocker,
    *,
    persisted: list[CreatedContainer] | None = None,
    persist: bool = True,
    **kwargs: object,
):
    sink = persisted if persisted is not None else []
    return container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000, **kwargs),  # type: ignore[arg-type]
        runner=docker,
        persist=sink.append if persist else None,
        home=tmp_path / "home",
        env_dir=tmp_path,
    )


def work_dir(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return work


def refusal(isolation: object, spec: Spec) -> CapabilityUnavailable:
    with pytest.raises(CapabilityUnavailable) as caught:
        isolation.wrap(["agent"], spec)  # type: ignore[attr-defined]
    assert caught.value.code.value == "SANDBOX_UNAVAILABLE"
    return caught.value


# -- registry and profile identity -----------------------------------------------------------------


def test_builtin_profiles_are_distinct_from_policy_profiles_and_none_needs_the_host_flag() -> None:
    registry = build_isolation_registry()
    assert registry.profiles() == {"worktree", "landlock", "skm:bubblewrap", "skm:seatbelt"}
    for policy_profile in ("read-only", "trusted-full-access", "workspace-contained"):
        with pytest.raises(CapabilityUnavailable) as caught:
            registry.get(policy_profile)
        assert caught.value.details["reason"] == "profile_not_registered"
    with pytest.raises(CapabilityUnavailable):
        registry.get("none")
    assert build_isolation_registry(allow_unconfined=True).get("none").profile == "none"


def test_an_unavailable_profile_never_resolves_to_a_weaker_one(tmp_path: Path) -> None:
    registry = build_isolation_registry()
    for missing in ("container", "none"):
        with pytest.raises(CapabilityUnavailable) as caught:
            registry.get(missing)
        assert caught.value.code.value == "SANDBOX_UNAVAILABLE"
    assert registry.get("landlock").profile == "landlock"


def test_plugin_profiles_use_the_namespaced_key_and_cannot_shadow_builtins() -> None:
    registry = build_isolation_registry()
    plugin = worktree_isolation()
    with pytest.raises(ValueError, match="plugin isolation key"):
        registry.register_plugin("none", plugin)
    with pytest.raises(ValueError, match="plugin isolation key"):
        registry.register_plugin("Bad Key:x", plugin)
    with pytest.raises(ValueError, match="declares profile"):
        registry.register_plugin("acme:strict", plugin)  # profile 'worktree' != key
    acme = type("Acme", (), {"profile": "acme:strict"})()
    registry.register_plugin("acme:strict", acme)  # type: ignore[arg-type]
    assert "acme:strict" in registry.profiles()
    with pytest.raises(ValueError, match="already registered"):
        registry.register_plugin("acme:strict", acme)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not a built-in"):
        IsolationRegistry({"acme:strict": acme})  # type: ignore[dict-item]


def test_none_is_unavailable_and_refuses_to_wrap_without_the_host_flag(tmp_path: Path) -> None:
    spec = Spec(work_dir(tmp_path))
    off = none_isolation()
    assert off.available(None)["available"] is False  # type: ignore[arg-type]
    assert refusal(off, spec).details["reason"] == "unconfined_not_allowed"
    on = none_isolation(allow_unconfined=True)
    wrapped = on.wrap(["agent", "--x"], spec)  # type: ignore[arg-type]
    assert wrapped.argv == ("agent", "--x")
    assert on.available(None)["available"] is True  # type: ignore[arg-type]


# -- coverage proof (§7.3) -------------------------------------------------------------------------


def test_worktree_alone_proves_nothing_and_is_refused_before_spawn(tmp_path: Path) -> None:
    error = refusal(worktree_isolation(), Spec(work_dir(tmp_path)))
    assert error.details["reason"] == "property_unproven"
    assert {"fs_write", "fs_read", "lifecycle", "network_none"} <= set(error.details["missing"])  # type: ignore[arg-type]


def make_launcher(tmp_path: Path) -> str:
    """An executable outside the unit's writable area, standing in for a companion's launcher."""
    path = tmp_path / "bin" / "skm-launch"
    path.parent.mkdir(exist_ok=True)
    path.write_text('#!/bin/sh\nexec "$@"\n')
    path.chmod(0o755)
    return str(path)


def cgroup_of(who: ProcessOwner) -> ProcessOwnership:
    return ProcessOwnership(owner=who, kind="cgroup", ref="/sys/fs/cgroup/skm/x")


def proving(
    name: str,
    claimed: Sequence[IsolationProperty],
    launcher: str,
    *,
    asked: list[ProofRequest] | None = None,
    **overrides: Any,
) -> Companion:
    """A companion whose verifier answers every request with a proof bound to that request, ``overrides``
    replacing proof fields (a forged binding, a relative launcher, foreign ownership...)."""

    def verify(request: ProofRequest) -> CompanionProof:
        if asked is not None:
            asked.append(request)
        proof = CompanionProof(
            frozenset(claimed),
            request.binding,
            (launcher,),
            "probe ok",
            cgroup_of(request.spec.owner) if P.LIFECYCLE in claimed else None,
        )
        return replace(proof, **overrides)

    return Companion(name, frozenset(claimed), verify)


EVERYTHING_BUT_EGRESS = (P.FS_WRITE, P.FS_READ, P.LIFECYCLE, P.CREDENTIALS, P.NETWORK_NONE)


def test_a_companion_is_a_verifier_not_a_label() -> None:
    with pytest.raises(ValueError, match="verify"):  # the old shape: a free-text evidence string
        Companion("sandbox", frozenset({P.FS_READ}), "probe ok")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Companion("sandbox", frozenset({P.FS_READ}))  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="at least one property"):
        Companion("sandbox", frozenset(), lambda request: None)  # type: ignore[arg-type,return-value]


def test_network_allowlist_without_an_egress_boundary_is_unavailable(tmp_path: Path) -> None:
    launcher = make_launcher(tmp_path)
    everything_but_egress = proving("native-sandbox", EVERYTHING_BUT_EGRESS, launcher)
    isolation = worktree_isolation(companions=(everything_but_egress,))
    spec = Spec(work_dir(tmp_path), network="allowlist", network_hosts=("api.example.com",))
    error = refusal(isolation, spec)
    assert error.details["missing"] == ["network_allowlist"]
    egress = proving("egress-proxy", (P.NETWORK_ALLOWLIST,), launcher)
    admitted = worktree_isolation(companions=(everything_but_egress, egress)).wrap(["agent"], spec)  # type: ignore[arg-type]
    assert admitted.ownership.kind == "cgroup"
    assert admitted.argv == (launcher, launcher, "agent")  # both launchers enforce before the command starts


def test_a_bound_proof_is_asked_the_exact_request_and_its_launcher_starts_the_command(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    asked: list[ProofRequest] = []
    launcher = make_launcher(tmp_path)
    spec = Spec(work, network="allowlist", network_hosts=("api.example.com",), env={"A": "1"})
    companion = proving("composite", (*EVERYTHING_BUT_EGRESS, P.NETWORK_ALLOWLIST), launcher, asked=asked)
    wrapped = worktree_isolation(companions=(companion,)).wrap(["agent", "--x"], spec)  # type: ignore[attr-defined]
    assert wrapped.argv == (launcher, "agent", "--x")
    (request,) = asked
    assert request.argv == ("agent", "--x")
    assert request.spec.network_hosts == ("api.example.com",)
    assert request.binding == request_binding("worktree", spec, ["agent", "--x"])  # type: ignore[arg-type]


def test_the_request_binding_covers_paths_hosts_launch_and_context(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    base = Spec(work, network="allowlist", network_hosts=("a.example",))
    reference = request_binding("worktree", base, ["agent"])  # type: ignore[arg-type]
    assert reference == request_binding("worktree", base, ("agent",))  # type: ignore[arg-type]

    def bind(
        profile: str = "worktree", argv: Sequence[str] = ("agent",), context: Any = None, **fields: Any
    ) -> str:
        spec = Spec(work, **{"network": "allowlist", "network_hosts": ("a.example",), **fields})
        return request_binding(profile, spec, argv, context)  # type: ignore[arg-type]

    variants = {
        "argv": bind(argv=["agent", "--more"]),
        "profile": bind("landlock"),
        "context": bind(context={"network": "other"}),
        "host": bind(network_hosts=("b.example",)),
        "writable": bind(writable=(work, tmp_path)),
        "readable": bind(readable=(tmp_path,)),
        "protected": bind(protected=(work / ".git",)),
        "network": bind(network="full", network_hosts=()),
        "env": bind(env={"X": "1"}),
    }
    assert all(value != reference for value in variants.values())
    assert len({*variants.values()}) == len(variants)


def test_a_forged_or_unbound_companion_proof_is_refused_before_spawn(tmp_path: Path) -> None:
    launcher = make_launcher(tmp_path)
    spec = Spec(work_dir(tmp_path))
    forged = proving("forged", EVERYTHING_BUT_EGRESS, launcher, binding="0" * 64)
    error = refusal(worktree_isolation(companions=(forged,)), spec)
    assert error.details["reason"] == "companion_proof_unbound"
    assert error.details["component"] == "forged"


def test_a_proof_for_other_paths_hosts_or_launch_cannot_be_replayed(tmp_path: Path) -> None:
    """A proof earned for one request is cached by a careless companion and replayed for another: refused."""
    launcher = make_launcher(tmp_path)
    work = work_dir(tmp_path)
    cache: list[CompanionProof] = []

    def replaying(request: ProofRequest) -> CompanionProof:
        if not cache:
            owned = cgroup_of(request.spec.owner)
            cache.append(CompanionProof(frozenset(request.needed), request.binding, (launcher,), "ok", owned))
        return cache[0]

    companion = Companion("replay", frozenset(EVERYTHING_BUT_EGRESS), replaying)
    isolation = worktree_isolation(companions=(companion,))
    first = Spec(work, network="none")
    assert isolation.wrap(["agent"], first)  # type: ignore[attr-defined]
    cases = {
        "other command": (["other"], Spec(work, network="none", owner=first.owner)),
        "other path": (["agent"], Spec(work, network="none", owner=first.owner, writable=(work, tmp_path))),
        "other readable": (["agent"], Spec(work, network="none", owner=first.owner, readable=(tmp_path,))),
        "other owner": (["agent"], Spec(work, network="none")),
    }
    for label, (argv, spec) in cases.items():
        with pytest.raises(CapabilityUnavailable) as caught:
            isolation.wrap(argv, spec)  # type: ignore[attr-defined]
        assert caught.value.details["reason"] == "companion_proof_unbound", label


def test_a_proof_for_other_network_hosts_cannot_be_replayed(tmp_path: Path) -> None:
    launcher = make_launcher(tmp_path)
    work = work_dir(tmp_path)
    owner = make_owner()
    first_binding: list[str] = []

    def verify(request: ProofRequest) -> CompanionProof:
        if not first_binding:
            first_binding.append(request.binding)
        return CompanionProof(
            frozenset(request.needed), first_binding[0], (launcher,), "ok", cgroup_of(owner)
        )

    companion = Companion("egress", frozenset({*EVERYTHING_BUT_EGRESS, P.NETWORK_ALLOWLIST}), verify)
    isolation = worktree_isolation(companions=(companion,))
    granted = Spec(work, network="allowlist", network_hosts=("api.example.com",), owner=owner)
    assert isolation.wrap(["agent"], granted)  # type: ignore[attr-defined]
    widened = Spec(work, network="allowlist", network_hosts=("api.example.com", "evil.example"), owner=owner)
    assert refusal(isolation, widened).details["reason"] == "companion_proof_unbound"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"properties": frozenset({P.NETWORK_ALLOWLIST})}, "companion_proof_overclaim"),
        ({"properties": frozenset()}, "companion_proof_overclaim"),
        ({"evidence": "   "}, "companion_proof_invalid"),
        ({"launch": ()}, "companion_launch_untrusted"),
        ({"launch": ("skm-launch",)}, "companion_launch_untrusted"),  # PATH lookup in an untrusted cwd
        ({"launch": ("/nonexistent/launcher",)}, "companion_launch_untrusted"),
        ({"ownership": None}, "companion_ownership_invalid"),
    ],
)
def test_a_proof_that_does_not_enforce_or_overclaims_is_refused(
    tmp_path: Path, overrides: dict[str, Any], reason: str
) -> None:
    launcher = make_launcher(tmp_path)
    companion = proving("native-sandbox", EVERYTHING_BUT_EGRESS, launcher, **overrides)
    assert (
        refusal(worktree_isolation(companions=(companion,)), Spec(work_dir(tmp_path))).details["reason"]
        == reason
    )


def test_a_proof_with_foreign_or_best_effort_ownership_is_refused(tmp_path: Path) -> None:
    launcher = make_launcher(tmp_path)

    def isolation(**kw: Any) -> object:
        return worktree_isolation(companions=(proving("cgroup", EVERYTHING_BUT_EGRESS, launcher, **kw),))

    spec = Spec(work_dir(tmp_path))
    foreign = ProcessOwnership(owner=make_owner("m" * 32), kind="cgroup", ref="/sys/fs/cgroup/skm/other")
    assert refusal(isolation(ownership=foreign), spec).details["reason"] == "companion_ownership_invalid"
    best_effort = ProcessOwnership(owner=spec.owner, kind="pgroup_best_effort", ref="pgroup:1")
    assert refusal(isolation(ownership=best_effort), spec).details["reason"] == "companion_ownership_invalid"


def test_a_launcher_the_unit_can_write_is_refused(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    inside = work / "launch"
    inside.write_text("#!/bin/sh\n")
    inside.chmod(0o755)
    companion = proving("native-sandbox", EVERYTHING_BUT_EGRESS, str(inside))
    error = refusal(worktree_isolation(companions=(companion,)), Spec(work))
    assert error.details["reason"] == "companion_launch_untrusted"
    link = tmp_path / "bin"
    link.mkdir()
    (link / "via-link").symlink_to(inside)  # a symlink into the writable tree is resolved first
    companion = proving("native-sandbox", EVERYTHING_BUT_EGRESS, str(link / "via-link"))
    assert (
        refusal(worktree_isolation(companions=(companion,)), Spec(work)).details["reason"]
        == "companion_launch_untrusted"
    )


def test_an_unknown_verification_result_is_unproven_not_assumed(tmp_path: Path) -> None:
    def boom(request: ProofRequest) -> CompanionProof:
        raise TimeoutError("probe timed out")

    spec = Spec(work_dir(tmp_path))
    failing = Companion("probe", frozenset(EVERYTHING_BUT_EGRESS), boom)
    assert (
        refusal(worktree_isolation(companions=(failing,)), spec).details["reason"] == "companion_proof_failed"
    )
    not_a_proof = Companion("probe", frozenset(EVERYTHING_BUT_EGRESS), lambda request: "verified")  # type: ignore[arg-type,return-value]
    assert (
        refusal(worktree_isolation(companions=(not_a_proof,)), spec).details["reason"]
        == "companion_proof_invalid"
    )


def test_a_companion_is_consulted_only_for_a_gap_the_backend_cannot_close(tmp_path: Path) -> None:
    asked: list[ProofRequest] = []
    launcher = make_launcher(tmp_path)
    irrelevant = proving("quota", (P.DISK_QUOTA,), launcher, asked=asked)
    error = refusal(worktree_isolation(companions=(irrelevant,)), Spec(work_dir(tmp_path)))
    assert error.details["reason"] == "property_unproven"
    assert asked == []  # nothing it may prove was missing, so its verifier never ran and no launcher is added


def test_assess_reports_requirement_proof_and_gap() -> None:
    with pytest.raises(CapabilityUnavailable) as caught:
        assess("landlock", frozenset({P.FS_WRITE, P.DISK_QUOTA}), {P.FS_WRITE: "landlock ABI 3"})
    coverage: Any = caught.value.details["coverage"]
    assert coverage["required"] == ["disk_quota", "fs_write"]
    assert coverage["proven"] == {"fs_write": "landlock ABI 3"}
    assert caught.value.details["missing"] == ["disk_quota"]


def test_spec_requirements_follow_the_requested_network_and_credentials(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    assert spec_requirements(Spec(work, network="full")) == {P.FS_WRITE, P.FS_READ, P.LIFECYCLE}  # type: ignore[arg-type]
    wanted = Spec(work, network="allowlist", credential_mounts=({"source": "/a", "target": "b"},))
    assert spec_requirements(wanted) == {  # type: ignore[arg-type]
        P.FS_WRITE, P.FS_READ, P.LIFECYCLE, P.NETWORK_ALLOWLIST, P.CREDENTIALS,
    }  # fmt: skip
    assert spec_requirements(Spec(work), confined=False) == frozenset()  # type: ignore[arg-type]


# -- permission rendering --------------------------------------------------------------------------


def test_read_only_profile_requires_confined_read_write_network_none_and_lifecycle() -> None:
    required = isolation_requirements(permissions("read-only"))
    assert required == {P.FS_WRITE, P.FS_READ, P.LIFECYCLE, P.NETWORK_NONE}


def test_a_read_layer_unrestricted_only_for_scope_any_still_requires_fs_read() -> None:
    """F8: ``any:**`` matches only paths outside every scope root; it grants no home, worktree or tmp."""
    trusted = permissions("trusted-full-access")
    assert P.FS_READ not in isolation_requirements(trusted), "every scope readable and nothing denied"
    any_only = PathPolicy((PathRule(PathScope.ANY, "**"),), ())
    assert not any_only.allows(ScopedPath(PathScope.HOME, None, "secret"))
    narrowed = replace(trusted, fs_read=(any_only,))
    assert P.FS_READ in isolation_requirements(narrowed)
    assert P.FS_READ in isolation_requirements(replace(trusted, fs_read=(*trusted.fs_read, any_only)))
    everything_but_home = PathPolicy(
        tuple(PathRule(scope, "**") for scope in PathScope if scope is not PathScope.HOME), ()
    )
    assert P.FS_READ in isolation_requirements(replace(trusted, fs_read=(everything_but_home,)))
    one_mount = PathPolicy(
        tuple(PathRule(scope, "**", "m" if scope is PathScope.WORKTREE else None) for scope in PathScope), ()
    )
    assert P.FS_READ in isolation_requirements(replace(trusted, fs_read=(one_mount,)))
    denying = PathPolicy(unrestricted_policy().allow, (PathRule(PathScope.HOME, ".ssh/**"),))
    assert P.FS_READ in isolation_requirements(replace(trusted, fs_read=(denying,)))
    assert P.FS_READ not in isolation_requirements(replace(trusted, fs_read=(unrestricted_policy(),)))


def test_allowlist_network_requires_an_egress_boundary_and_an_empty_one_is_none() -> None:
    allowlist = {"policy.ceiling.network": "allowlist"}
    pypi: list[JsonValue] = ["pypi.org"]
    unrelated: list[JsonValue] = ["unrelated.example"]
    hosts = permissions("workspace-contained", **allowlist, **{"policy.ceiling.network_allowlist": pypi})
    assert hosts.network.mode.value == "allowlist"
    required = isolation_requirements(hosts)
    assert P.NETWORK_ALLOWLIST in required
    assert P.NETWORK_NONE not in required
    # the conjunction admits no host: rendered as ``none``, as ``view_document`` does, never as an open list
    disjoint = permissions(
        "workspace-contained", **allowlist, **{"policy.ceiling.network_allowlist": unrelated}
    )
    assert isolation_requirements(disjoint) >= {P.NETWORK_NONE}
    assert P.NETWORK_ALLOWLIST not in isolation_requirements(disjoint)


def test_unrestricted_network_and_extra_flags_are_rendered_exactly() -> None:
    trusted = permissions("trusted-full-access")
    assert trusted.network.mode.value == "any"
    base = isolation_requirements(trusted)
    assert not {P.NETWORK_NONE, P.NETWORK_ALLOWLIST} & base
    flagged = isolation_requirements(trusted, credentials=True, resources=True, disk_quota=True, config=True)
    assert flagged - base == {P.CREDENTIALS, P.RESOURCES, P.DISK_QUOTA, P.CONFIG}


# -- container: argv -------------------------------------------------------------------------------


def test_create_argv_is_non_root_read_only_capless_pinned_and_labelled(tmp_path: Path) -> None:
    docker = FakeDocker()
    work = work_dir(tmp_path)
    spec = Spec(work, env={"PATH": "/usr/bin", "HOME": "/root"})
    argv = container_backend(tmp_path, docker).create_argv(["agent", "-p"], spec, env_file=None)  # type: ignore[attr-defined]
    joined = " ".join(argv)
    for expected in (
        "--user 1000:1000", "--cap-drop ALL", "--security-opt no-new-privileges", "--read-only",
        "--network none", "--pull never", "--workdir /work", "--pids-limit 512", "--memory 4g", "--cpus 2",
        f"--name skm-step-{spec.owner.unit_id}", "--env HOME=/home/skm", "--env PATH=/usr/bin",
        f"--label skm.owner_nonce={spec.owner.owner_nonce}", "--tmpfs /tmp:rw,nosuid,nodev,size=1g",
    ):  # fmt: skip
        assert expected in joined, expected
    assert "HOME=/root" not in joined
    assert argv[-4:] == (IMAGE, "agent", "-p")[-4:] or argv[-3:] == (IMAGE, "agent", "-p")
    assert f"type=bind,src={work},dst=/work" in joined
    assert "--privileged" not in joined
    assert "--rm" not in argv


def test_read_only_roles_get_a_readonly_workdir_mount_and_materials_are_readonly(tmp_path: Path) -> None:
    work, materials = work_dir(tmp_path), tmp_path / "materials"
    materials.mkdir()
    spec = Spec(work, writable=(), readable=(work, materials), materials_dir=materials)
    joined = " ".join(container_backend(tmp_path, FakeDocker()).create_argv(["a"], spec, env_file=None))  # type: ignore[attr-defined]
    assert f"type=bind,src={work},dst=/work,readonly" in joined
    assert f"type=bind,src={materials},dst=/materials,readonly" in joined


def test_no_grant_means_no_mount_of_the_workdir_or_the_materials(tmp_path: Path) -> None:
    work, materials = work_dir(tmp_path), tmp_path / "materials"
    materials.mkdir()
    spec = Spec(work, writable=(), readable=(), materials_dir=materials)
    joined = " ".join(container_backend(tmp_path, FakeDocker()).create_argv(["a"], spec, env_file=None))  # type: ignore[attr-defined]
    assert "--mount" not in joined


def test_a_narrow_read_grant_mounts_only_that_directory_never_the_whole_workdir_or_materials(
    tmp_path: Path,
) -> None:
    """F2: ``readable=(work/public,)`` must not expose ``work/private`` through a whole-workdir bind."""
    work, materials = work_dir(tmp_path), tmp_path / "materials"
    (work / "public").mkdir()
    (work / "private").mkdir()
    (work / "private" / "secret").write_text("s")
    (materials / "docs").mkdir(parents=True)
    (materials / "other").mkdir()
    spec = Spec(work, writable=(), readable=(work / "public", materials / "docs"), materials_dir=materials)
    argv = container_backend(tmp_path, FakeDocker()).create_argv(["a"], spec, env_file=None)  # type: ignore[attr-defined]
    mounts = [item for flag, item in itertools.pairwise(argv) if flag == "--mount"]
    assert mounts == [
        f"type=bind,src={work / 'public'},dst=/work/public,readonly",
        f"type=bind,src={materials / 'docs'},dst=/materials/docs,readonly",
    ]


def test_a_narrow_write_grant_does_not_expose_its_siblings_and_a_nested_write_is_not_widened(
    tmp_path: Path,
) -> None:
    work = work_dir(tmp_path)
    (work / "out").mkdir()
    (work / "src").mkdir()
    only_out = Spec(work, writable=(work / "out",))
    argv = container_backend(tmp_path, FakeDocker()).create_argv(["a"], only_out, env_file=None)  # type: ignore[attr-defined]
    assert [item for flag, item in itertools.pairwise(argv) if flag == "--mount"] == [
        f"type=bind,src={work / 'out'},dst=/work/out"
    ]
    # a writable directory below a read-only workdir grant stays writable, the rest of the workdir read-only
    mixed = Spec(work, writable=(work / "out",), readable=(work,))
    argv = container_backend(tmp_path, FakeDocker()).create_argv(["a"], mixed, env_file=None)  # type: ignore[attr-defined]
    assert [item for flag, item in itertools.pairwise(argv) if flag == "--mount"] == [
        f"type=bind,src={work},dst=/work,readonly",
        f"type=bind,src={work / 'out'},dst=/work/out",
    ]


def test_credentials_mount_readonly_below_container_home_and_reject_escapes(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    auth = tmp_path / "auth.json"
    auth.write_text("{}")
    backend = container_backend(tmp_path, FakeDocker())
    good = Spec(work, credential_mounts=({"source": str(auth), "target": ".config/auth.json"},))
    assert f"type=bind,src={auth},dst=/home/skm/.config/auth.json,readonly" in " ".join(
        backend.create_argv(["a"], good, env_file=None)  # type: ignore[attr-defined]
    )
    for target in ("../escape", "/etc/passwd", "a,dst=/etc"):
        bad = Spec(work, credential_mounts=({"source": str(auth), "target": target},))
        assert refusal(backend, bad).details["reason"] == "credential_mount_invalid"


@pytest.mark.parametrize(
    "source",
    ["/var/run/docker.sock", "/run/docker.sock", "/var/run", "/", "HOME", "relative/path", "/tmp/a,dst=/etc"],  # noqa: S108
)
def test_docker_socket_home_and_unsafe_mount_sources_are_never_mounted(tmp_path: Path, source: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = Path(source.replace("HOME", str(home)))
    spec = Spec(work_dir(tmp_path), readable=(path,))
    assert refusal(container_backend(tmp_path, FakeDocker()), spec).details["reason"] in {
        "forbidden_mount",
        "unsafe_mount_path",
    }


def test_container_cannot_bind_hookd_runtime_or_a_parent_before_daemon_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = work_dir(tmp_path)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(work / "runtime"))
    error = refusal(container_backend(tmp_path, FakeDocker()), Spec(work, readable=(work,), writable=()))
    assert error.details["reason"] == "forbidden_mount"
    assert error.details["exposes"] == "hookd runtime"


def test_a_checkout_below_the_home_may_be_mounted_but_the_home_itself_may_not(tmp_path: Path) -> None:
    home = tmp_path / "home"
    checkout = home / "projects" / "app"
    checkout.mkdir(parents=True)
    argv = container_backend(tmp_path, FakeDocker()).create_argv(["a"], Spec(checkout), env_file=None)  # type: ignore[attr-defined]
    assert f"src={checkout}," in " ".join(argv)


def test_protected_path_inside_a_writable_mount_becomes_a_readonly_hole(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    git_dir = work / ".git"
    git_dir.mkdir()
    backend = container_backend(tmp_path, FakeDocker())
    joined = " ".join(backend.create_argv(["a"], Spec(work, protected=(git_dir,)), env_file=None))  # type: ignore[attr-defined]
    assert f"type=bind,src={git_dir},dst=/work/.git,readonly" in joined
    overlap = Spec(work, writable=(git_dir,), protected=(work,))
    assert refusal(backend, overlap).details["reason"] == "protected_overlap"


def mount_list(argv: Sequence[str]) -> list[str]:
    return [item for flag, item in itertools.pairwise(argv) if flag == "--mount"]


def test_protected_path_is_read_only_at_every_alias_a_writable_ancestor_grant_creates(tmp_path: Path) -> None:
    """F5: ``/srv/outer`` writable beside the workdir ``/srv/outer/inner`` exposes the protected ``.git`` at a
    second destination; both must be read-only holes."""
    outer = tmp_path / "outer"
    inner = outer / "inner"
    git_dir = inner / ".git"
    git_dir.mkdir(parents=True)
    spec = Spec(inner, writable=(inner, outer), protected=(git_dir,))
    mounts = mount_list(container_backend(tmp_path, FakeDocker()).create_argv(["a"], spec, env_file=None))  # type: ignore[attr-defined]
    assert f"type=bind,src={inner},dst=/work" in mounts
    assert f"type=bind,src={outer},dst={outer}" in mounts
    assert f"type=bind,src={git_dir},dst=/work/.git,readonly" in mounts
    assert f"type=bind,src={git_dir},dst={git_dir},readonly" in mounts
    writable_targets = {item.split("dst=")[1] for item in mounts if not item.endswith(",readonly")}
    assert writable_targets == {"/work", str(outer)}


def test_protected_path_that_is_missing_or_is_itself_a_writable_mount_is_refused(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    backend = container_backend(tmp_path, FakeDocker())
    missing = Spec(work, protected=(work / ".git",))  # the command could create it inside the writable mount
    assert refusal(backend, missing).details["reason"] == "protected_overlap"
    assert refusal(backend, Spec(work, protected=(work,))).details["reason"] == "protected_overlap"


def test_a_symlinked_protected_path_is_resolved_before_the_hole_is_cut(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    real = work / "meta"
    real.mkdir()
    (work / "alias").symlink_to(real)
    argv = container_backend(tmp_path, FakeDocker()).create_argv(  # type: ignore[attr-defined]
        ["a"], Spec(work, protected=(work / "alias",)), env_file=None
    )
    assert f"type=bind,src={real},dst=/work/meta,readonly" in mount_list(argv)


def test_rootless_docker_sockets_and_every_runtime_directory_are_never_mounted(tmp_path: Path) -> None:
    """F1: only two system socket paths were refused; ``/run/user/<uid>/docker.sock`` (rootless) passed."""
    backend = container_backend(tmp_path, FakeDocker())
    work = work_dir(tmp_path)
    for source in (
        "/run/user/1000/docker.sock",
        "/run/user/1000",
        "/run/containerd/containerd.sock",
        "/run/podman/podman.sock",
        "/var/lib/docker",
        "/var/lib/docker/volumes",
        "/var/lib/containerd",
    ):
        assert (
            refusal(backend, Spec(work, readable=(Path(source),))).details["reason"] == "forbidden_mount"
        ), source
        assert (
            refusal(backend, Spec(work, writable=(work, Path(source)))).details["reason"] == "forbidden_mount"
        )
    for item in (".docker", ".docker/desktop/docker.sock", ".local/share/docker"):
        assert refusal(backend, Spec(work, readable=(tmp_path / "home" / item,))).details["reason"] == (
            "forbidden_mount"
        )


def test_a_unix_socket_anywhere_or_directly_inside_a_mount_source_is_never_mounted(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    holder = tmp_path / "elsewhere"
    holder.mkdir()
    sock = holder / "daemon.sock"
    os.mknod(sock, stat.S_IFSOCK | 0o600)  # a socket node without binding one: the type is what is refused
    link = tmp_path / "link"
    link.symlink_to(sock)
    backend = container_backend(tmp_path, FakeDocker())
    assert refusal(backend, Spec(work, readable=(sock,))).details["exposes"] == str(sock)
    assert refusal(backend, Spec(work, readable=(holder,))).details["exposes"] == str(sock)
    assert refusal(backend, Spec(work, readable=(link,))).details["exposes"] == str(sock)
    credential = Spec(work, credential_mounts=({"source": str(link), "target": "x"},))
    assert refusal(backend, credential).details["reason"] == "forbidden_mount"
    (work / "run.sock").unlink(missing_ok=True)
    os.mknod(work / "run.sock", stat.S_IFSOCK | 0o600)
    assert refusal(backend, Spec(work)).details["exposes"] == str(work / "run.sock"), (
        "a socket in the workdir"
    )


def test_a_nested_unix_socket_inside_a_mount_source_is_never_mounted(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    nested = work / "sub" / "nested"
    nested.mkdir(parents=True)
    (nested / "loop").symlink_to(work)
    sock = nested / "proxy.sock"
    os.mknod(sock, stat.S_IFSOCK | 0o600)
    backend = container_backend(tmp_path, FakeDocker())
    error = refusal(backend, Spec(work))
    assert error.details["reason"] == "forbidden_mount"
    assert error.details["exposes"] == str(sock)
    clean = tmp_path / "clean"
    clean.mkdir()
    assert refusal(backend, Spec(clean, readable=(work,))).details["exposes"] == str(sock)
    sock.unlink()
    argv = backend.create_argv(["a"], Spec(work), env_file=None)  # type: ignore[attr-defined]
    assert f"src={work}," in " ".join(argv)


def test_the_socket_of_docker_host_is_never_mounted(tmp_path: Path) -> None:
    daemon_dir = tmp_path / "custom"
    daemon_dir.mkdir()
    (daemon_dir / "engine.sock").write_text("not a real socket, only a named path")
    work = work_dir(tmp_path)
    host_env = {"DOCKER_HOST": f"unix://{daemon_dir / 'engine.sock'}"}
    backend = container_backend(tmp_path, FakeDocker())
    for source in (daemon_dir / "engine.sock", daemon_dir):
        spec = Spec(work, readable=(source,), env=host_env)
        assert refusal(backend, spec).details["reason"] == "forbidden_mount"
    via_client = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=FakeDocker(),
        persist=lambda created: None,
        home=tmp_path / "home",
        client_env=host_env,
    )
    assert refusal(via_client, Spec(work, readable=(daemon_dir / "engine.sock",))).details["reason"] == (
        "forbidden_mount"
    )


def test_unrecognised_variable_names_never_put_their_values_on_the_docker_argv(tmp_path: Path) -> None:
    # A name heuristic misses DSNs and vendor keys such as OPENROUTER_KEY; the argv is world-readable.
    docker = FakeDocker()
    work = work_dir(tmp_path)
    dsn = "postgresql://app:hunter2-pass@db/app"
    spec = Spec(work, env={"LANG": "C", "DATABASE_URL": dsn, "OPENROUTER_KEY": "or-v1-value"})
    container_backend(tmp_path, docker).wrap(["agent"], spec)  # type: ignore[attr-defined]
    create = " ".join(next(call for call in docker.calls if call[1] == "create"))
    assert dsn not in create
    assert "or-v1-value" not in create
    assert "--env LANG=C" in create
    assert docker.env_files == [(0o600, f"DATABASE_URL={dsn}\nOPENROUTER_KEY=or-v1-value\n")]


@pytest.mark.parametrize("name", ["API_TOKEN", "LC_API_TOKEN"])
def test_secret_named_variables_use_a_0600_env_file_and_never_the_argv(tmp_path: Path, name: str) -> None:
    docker = FakeDocker()
    work = work_dir(tmp_path)
    spec = Spec(work, env={"PATH": "/usr/bin", "HOME": "/host-home", "LC_ALL": "C", name: "s3cr3t-value"})
    wrapped = container_backend(tmp_path, docker).wrap(["agent"], spec)  # type: ignore[attr-defined]
    create = next(call for call in docker.calls if call[1] == "create")
    assert "s3cr3t-value" not in " ".join(create)
    assert name not in " ".join(create)
    assert "HOME=/home/skm" in create
    assert "HOME=/host-home" not in create
    assert "LC_ALL=C" in create
    assert docker.env_files == [(0o600, f"{name}=s3cr3t-value\n")]
    assert not list(tmp_path.glob("skm-env-*")), "the env file is removed once the daemon has read it"
    assert "s3cr3t-value" not in " ".join(wrapped.argv)


def test_a_failed_env_file_write_leaves_no_partial_secret_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fdopen = os.fdopen

    class FullDisk(io.TextIOWrapper):
        @override
        def write(self, text: str, /) -> int:
            super().write(text[: len(text) // 2])
            self.flush()
            raise OSError(errno.ENOSPC, "No space left on device")

    def fdopen(fd: int, mode: str = "r", *args: Any, **kwargs: Any) -> IO[Any]:
        if mode != "w":
            return real_fdopen(fd, mode, *args, **kwargs)
        return FullDisk(io.BufferedWriter(io.FileIO(fd, "w")), encoding="utf-8")

    monkeypatch.setattr(os, "fdopen", fdopen)
    spec = Spec(work_dir(tmp_path), env={"API_TOKEN": "s3cr3t-value"})
    with pytest.raises(OSError, match="No space left"):
        container_backend(tmp_path, FakeDocker()).wrap(["agent"], spec)  # type: ignore[attr-defined]
    assert not list(tmp_path.glob("skm-env-*")), "no partial secret file is left behind"


def test_invalid_environment_names_or_values_are_refused(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    for env in ({"BAD NAME": "x"}, {"OK": "line1\nline2"}):
        assert refusal(container_backend(tmp_path, FakeDocker()), Spec(work, env=env)).details["reason"] == (
            "env_invalid"
        )


# -- container: settings and network ---------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"image": "registry.example/skm-cli:latest"},
        {"image": "registry.example/skm-cli@sha256:abc"},
        {"uid": 0},
        {"gid": 0},
        {"memory": "lots"},
        {"pids_limit": 1},
        {"network": "bad name"},
    ],
)
def test_settings_require_a_digest_pinned_image_a_non_root_user_and_sane_limits(
    fields: dict[str, object],
) -> None:
    values: dict[str, object] = {"image": IMAGE, "uid": 1000, "gid": 1000, **fields}
    with pytest.raises(ValueError, match=r"."):
        ContainerSettings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("options", "remapped_by"),
    [
        ('["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]', ["rootless"]),
        ('["name=userns"]', ["userns"]),
        ('["name=rootless","name=userns"]', ["rootless", "userns"]),
    ],
)
def test_a_daemon_that_remaps_uids_refuses_a_writable_mount_before_create(
    tmp_path: Path, options: str, remapped_by: list[str]
) -> None:
    """``--user 1000:1000`` on a rootless daemon is subuid 100999 on the host: the worker's own 0775 workdir
    refuses it, and the unit would only find out at its first write after the spawn."""
    docker, persisted = FakeDocker(), []
    docker.security_options = options
    error = refusal(container_backend(tmp_path, docker, persisted=persisted), Spec(work_dir(tmp_path)))
    assert error.details["reason"] == "daemon_uid_not_identity"
    assert error.details["remapped_by"] == remapped_by
    assert "create" not in docker.verbs()
    assert persisted == []


@pytest.mark.parametrize("options", ["", "null", "{}", "not json", "[1]", '{"name": "rootless"}'])
def test_a_daemon_that_does_not_report_its_uid_mapping_is_not_assumed_to_be_identity(
    tmp_path: Path, options: str
) -> None:
    docker = FakeDocker()
    docker.security_options = options
    error = refusal(container_backend(tmp_path, docker), Spec(work_dir(tmp_path)))
    assert error.details["reason"] == "daemon_uid_mapping_unproven"
    assert "create" not in docker.verbs()


def test_a_failing_uid_mapping_query_is_unproven_not_identity(tmp_path: Path) -> None:
    docker = FakeDocker()

    def runner(argv: Sequence[str]) -> DockerResult:
        return DockerResult(1, "[]", "boom") if "SecurityOptions" in argv[-1] else docker(argv)

    isolation = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=lambda created: None,
        home=tmp_path / "home",
    )
    assert refusal(isolation, Spec(work_dir(tmp_path))).details["reason"] == "daemon_uid_mapping_unproven"
    assert "create" not in docker.verbs()


def test_a_remapping_daemon_still_serves_a_read_only_unit_as_the_same_non_root_user(tmp_path: Path) -> None:
    docker = FakeDocker()
    docker.security_options = '["name=rootless"]'
    work = work_dir(tmp_path)
    spec = Spec(work, writable=(), readable=(work,))
    assert container_backend(tmp_path, docker).wrap(["agent"], spec).argv[:2] == ("docker", "start")  # type: ignore[attr-defined]
    (create,) = [call for call in docker.calls if call[1] == "create"]
    assert create[create.index("--user") + 1] == "1000:1000"
    assert f"type=bind,src={work},dst=/work,readonly" in create
    assert not any(item.startswith("--userns") for item in create)


def test_an_identity_daemon_keeps_the_writable_mount_and_asks_for_the_mapping_only_then(
    tmp_path: Path,
) -> None:
    docker = FakeDocker()
    work = work_dir(tmp_path)
    backend = container_backend(tmp_path, docker)
    backend.wrap(["agent"], Spec(work, writable=(), readable=(work,)))  # type: ignore[attr-defined]
    assert not any("{{json .SecurityOptions}}" in call for call in docker.calls)
    backend.wrap(["agent"], Spec(work, owner=make_owner("w" * 32)))  # type: ignore[attr-defined]
    assert any("{{json .SecurityOptions}}" in call for call in docker.calls)
    assert docker.verbs().count("create") == 2


def left_by_a_dead_client(backend: Any, docker: FakeDocker, spec: Spec) -> str:
    """A container of ``spec.owner`` that a ``create`` left before anything was persisted or started."""
    return docker(backend.create_argv(["agent"], spec, env_file=None)).stdout.strip()


def assert_refused_untouched(docker: FakeDocker, persisted: list[CreatedContainer], *kept: str) -> None:
    assert persisted == []
    assert not {"create", "start", "stop", "kill", "rm"} & set(docker.verbs())
    assert all(docker.containers[container_id]["state"] == "created" for container_id in kept)


@pytest.mark.parametrize("options", ['["name=rootless"]', '["name=userns"]'])
def test_a_recovered_writable_container_is_not_started_on_a_remapping_daemon(
    tmp_path: Path, options: str
) -> None:
    """The check stood only on the way to ``create``: a retry that found the container got its start argv."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    unrelated = left_by_a_dead_client(backend, docker, Spec(spec.workdir, owner=make_owner("u" * 32)))
    docker.security_options = options
    docker.calls.clear()
    assert refusal(backend, spec).details["reason"] == "daemon_uid_not_identity"
    assert_refused_untouched(docker, persisted, mine, unrelated)
    assert all(call[-1] != unrelated for call in docker.calls)


@pytest.mark.parametrize("options", ["", "null", "not json", "[1]"])
def test_a_recovered_writable_container_needs_a_proven_mapping(tmp_path: Path, options: str) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.security_options = options
    docker.calls.clear()
    assert refusal(backend, spec).details["reason"] == "daemon_uid_mapping_unproven"
    assert_refused_untouched(docker, persisted, mine)


@pytest.mark.parametrize(
    "report",
    [
        None,  # what ``create`` really mounted: the request below no longer says so
        "",
        "null",
        "not json",
        "[1]",
        '[{"Type": "bind"}]',
        '[{"Type": "bind", "RW": false}, {"Type": "bind", "RW": true}]',
    ],
)
def test_a_recovered_container_counts_its_own_mounts_not_only_the_request(
    tmp_path: Path, report: str | None
) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    owner = make_owner()
    mine = left_by_a_dead_client(backend, docker, Spec(work, owner=owner))
    if report is not None:
        docker.containers[mine]["mounts_report"] = report
    docker.security_options = '["name=rootless"]'
    docker.calls.clear()
    reader = Spec(work, writable=(), readable=(work,), owner=owner)
    assert refusal(backend, reader).details["reason"] == "daemon_uid_not_identity"
    assert_refused_untouched(docker, persisted, mine)


def test_a_recovered_container_that_lost_readonly_is_refused_like_a_writable_one(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    reader = Spec(work, writable=(), readable=(work,))
    mine = without_readonly(docker)(backend.create_argv(["agent"], reader, env_file=None)).stdout.strip()  # type: ignore[attr-defined]
    docker.security_options = '["name=rootless"]'
    docker.calls.clear()
    assert refusal(backend, reader).details["reason"] == "daemon_uid_not_identity"
    assert_refused_untouched(docker, persisted, mine)


def test_a_recovered_read_only_container_still_starts_on_a_remapping_daemon(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    reader = Spec(work, writable=(), readable=(work,))
    mine = left_by_a_dead_client(backend, docker, reader)
    docker.security_options = '["name=rootless"]'
    docker.calls.clear()
    wrapped = backend.wrap(["agent"], reader)  # type: ignore[attr-defined]
    assert wrapped.argv == ("docker", "start", "--attach", mine)
    assert [created.container_id for created in persisted] == [mine]
    assert "create" not in docker.owner_verbs()
    assert not any("{{json .SecurityOptions}}" in call for call in docker.calls)


def test_a_recovered_writable_container_still_starts_on_an_identity_daemon(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.calls.clear()
    assert backend.wrap(["agent"], spec).argv == ("docker", "start", "--attach", mine)  # type: ignore[attr-defined]
    assert any("{{json .SecurityOptions}}" in call for call in docker.calls)
    assert "create" not in docker.owner_verbs()


def test_a_volume_of_the_image_does_not_make_a_recovered_container_writable(tmp_path: Path) -> None:
    docker = FakeDocker()
    docker.image_config = {"Volumes": {"/data": {}}}
    backend = container_backend(tmp_path, docker)
    work = work_dir(tmp_path)
    reader = Spec(work, writable=(), readable=(work,))
    mine = left_by_a_dead_client(backend, docker, reader)
    [volume] = docker.containers[mine]["mounts"][-1:]
    assert (volume["Type"], volume["Destination"], volume["RW"]) == ("volume", "/data", True)
    docker.security_options = '["name=rootless"]'
    assert backend.wrap(["agent"], reader).argv[-1] == mine  # type: ignore[attr-defined]


# -- container: a recovered container runs what it was created with --------------------------------


def reader_of(work: Path, **fields: object) -> Spec:
    return Spec(work, writable=(), readable=(work,), **fields)


def changed(document: dict[str, Any], path: str, value: object) -> None:
    """Set ``value`` at the dotted ``path``; ``ABSENT`` removes the key."""
    *parents, last = path.split(".")
    for key in parents:
        document = document[key]
    if value is ABSENT:
        del document[last]
    else:
        document[last] = value


ABSENT = object()


def assert_mismatch(error: CapabilityUnavailable, mine: str, *fields: str) -> None:
    assert error.details["reason"] == "recovered_config_mismatch", error.details
    assert error.details["container_id"] == mine
    assert set(fields) <= set(error.details["differs"]), error.details  # type: ignore[arg-type]


def test_a_recovered_container_of_the_same_request_starts_by_its_id(tmp_path: Path) -> None:
    """The positive control of everything below: exact is not the same as never."""
    work = work_dir(tmp_path)
    materials = tmp_path / "materials"
    materials.mkdir()
    secret_free = {"LANG": "C.UTF-8", "PATH": "/opt/bin"}
    for spec in (
        Spec(work, env=secret_free, materials_dir=materials, readable=(materials,)),
        reader_of(work),
        Spec(work, writable=(), readable=()),  # no mount at all: Docker leaves the key out
    ):
        docker, persisted = FakeDocker(), []
        docker.image_config = {
            "Entrypoint": ["/init"],
            "Env": ["PATH=/image/bin", "IMAGE_ONLY=1"],
            "Labels": {"org.opencontainers.image.title": "cli"},
            "Volumes": {"/data": {}},
            "Healthcheck": {"Test": ["NONE"]},
        }
        backend = container_backend(tmp_path, docker, persisted=persisted)
        mine = left_by_a_dead_client(backend, docker, spec)
        docker.calls.clear()
        assert backend.wrap(["agent"], spec).argv == ("docker", "start", "--attach", mine)  # type: ignore[attr-defined]
        assert [created.container_id for created in persisted] == [mine]
        assert not {"create", "stop", "kill", "rm"} & set(docker.owner_verbs())
        assert docker.probe_verbs() == ["create", "inspect", "rm"]
        assert list(docker.containers) == [mine], "the probe is gone, the container remains"
        assert list(docker.volumes) == [docker.containers[mine]["mounts"][-1]["Name"]], "its volume stays too"


@pytest.mark.parametrize(
    ("entrypoint", "path", "args", "stored"),
    [
        ([""], "agent", [], None),
        ([], "agent", [], []),
        (None, "agent", [], None),
        (["", "x"], "", ["x", "agent"], ["", "x"]),
        (["/init"], "/init", ["agent"], ["/init"]),
    ],
    ids=["one-empty-string", "empty", "none", "empty-among-others", "real"],
)
def test_the_entrypoint_of_the_image_is_what_the_daemon_makes_of_it(
    tmp_path: Path, entrypoint: list[str] | None, path: str, args: list[str], stored: list[str] | None
) -> None:
    docker, persisted = FakeDocker(), []
    docker.image_config = {"Entrypoint": entrypoint}
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    record = docker.containers[mine]["record"]
    assert (record["Path"], record["Args"], record["Config"]["Entrypoint"]) == (path, args, stored)
    assert backend.wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Config.Entrypoint", [""]),
        ("Config.Entrypoint", ["/bin/evil"]),
        ("Path", "/bin/evil"),
        ("Args", ["agent", "--evil"]),
    ],
)
def test_an_empty_entrypoint_of_the_image_excuses_no_other_program(
    tmp_path: Path, field: str, value: object
) -> None:
    """The reset is the daemon's, so only what it leaves is accepted: no entrypoint and command as program."""
    docker, persisted = FakeDocker(), []
    docker.image_config = {"Entrypoint": [""]}
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    changed(docker.containers[mine]["record"], field, value)
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, field)
    assert_refused_untouched(docker, persisted, mine)


def test_a_reset_entrypoint_is_refused_where_the_image_has_a_real_one(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    docker.image_config = {"Entrypoint": ["/init"]}
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    argv = backend.create_argv(["agent"], spec, env_file=None)  # type: ignore[attr-defined]
    mine = create_with(docker, "--entrypoint", "")(argv).stdout.strip()
    assert docker.containers[mine]["record"]["Config"]["Entrypoint"] is None
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, "Config.Entrypoint", "Path", "Args")
    assert_refused_untouched(docker, persisted, mine)


def test_repeated_variables_of_the_image_merge_as_in_the_daemon_and_the_first_stays(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    docker.image_config = {"Env": ["TWICE=first", "NO_VALUE", "TWICE=second", "NO_VALUE=late", "ONCE=1"]}
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path), env={"LANG": "C"})
    mine = left_by_a_dead_client(backend, docker, spec)
    assert sorted(docker.containers[mine]["record"]["Config"]["Env"]) == [
        "HOME=/home/skm",
        "LANG=C",
        "NO_VALUE",
        "ONCE=1",
        "TWICE=first",
    ]
    assert backend.wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]


def test_repeated_variables_of_the_image_never_replace_those_of_the_request(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    docker.image_config = {"Env": ["LANG=evil", "LANG=evil-too", "HOME=/evil", "HOME=/evil-too"]}
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path), env={"LANG": "C"})
    mine = left_by_a_dead_client(backend, docker, spec)
    assert sorted(docker.containers[mine]["record"]["Config"]["Env"]) == ["HOME=/home/skm", "LANG=C"]
    assert backend.wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "env",
    [
        ["HOME=/home/skm", "LANG=C", "TWICE=second"],
        ["HOME=/home/skm", "LANG=C", "TWICE=first", "TWICE=second"],
        ["HOME=/home/skm", "LANG=C", "TWICE=first", "LANG=evil"],
        ["HOME=/home/skm", "LANG=evil", "TWICE=first"],
        ["HOME=/evil", "LANG=C", "TWICE=first"],
        ["HOME=/home/skm", "LANG=C"],
    ],
    ids=["later-line", "both-lines", "image-after-request", "image-instead-of-request", "home", "dropped"],
)
def test_an_environment_the_merge_would_not_produce_is_refused(tmp_path: Path, env: list[str]) -> None:
    docker, persisted = FakeDocker(), []
    docker.image_config = {"Env": ["TWICE=first", "TWICE=second", "LANG=evil", "HOME=/evil"]}
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path), env={"LANG": "C"})
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["Config"]["Env"] = env
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, "Config.Env")
    assert_refused_untouched(docker, persisted, mine)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Image", "sha256:" + "6" * 64),
        ("Path", "/bin/evil"),
        ("Args", ["-c", "evil"]),
        ("Config.Image", "registry.example/other@sha256:" + "b" * 64),
        ("Config.Cmd", ["evil"]),
        ("Config.Entrypoint", ["/bin/evil"]),
        ("Config.Env", ["HOME=/home/skm", "LD_PRELOAD=/evil.so"]),
        ("Config.Env", []),
        ("Config.User", "0:0"),
        ("Config.WorkingDir", "/"),
        ("Config.Volumes", {"/extra": {}}),
        ("Config.Healthcheck", {"Test": ["CMD", "evil"]}),
        ("Config.OpenStdin", True),
        ("Config.Tty", True),
        ("NetworkSettings.Networks", {"none": {}, "egress": {}}),
        ("NetworkSettings.Networks", {"bridge": {}}),
        ("HostConfig.NetworkMode", "host"),
        ("HostConfig.NetworkMode", "bridge"),
        ("HostConfig.Init", False),
        ("HostConfig.Privileged", True),
        ("HostConfig.ReadonlyRootfs", False),
        ("HostConfig.CapDrop", None),
        ("HostConfig.CapAdd", ["SYS_ADMIN"]),
        ("HostConfig.SecurityOpt", None),
        ("HostConfig.SecurityOpt", ["no-new-privileges", "seccomp=unconfined"]),
        ("HostConfig.Tmpfs", {"/tmp": "rw,exec,size=1g"}),  # noqa: S108
        ("HostConfig.Binds", ["/:/host"]),
        ("HostConfig.VolumesFrom", ["other"]),
        ("HostConfig.Memory", 0),
        ("HostConfig.MemorySwap", -1),
        ("HostConfig.NanoCpus", 0),
        ("HostConfig.PidsLimit", 0),
        ("HostConfig.PidMode", "host"),
        ("HostConfig.UTSMode", "host"),
        ("HostConfig.UsernsMode", "host"),
        ("HostConfig.IpcMode", "host"),
        ("HostConfig.CgroupnsMode", "host"),
        ("HostConfig.Runtime", "unconfined"),
        ("HostConfig.LogConfig.Type", "syslog"),
        ("HostConfig.RestartPolicy.Name", "always"),
        ("HostConfig.RestartPolicy.MaximumRetryCount", 3),
        ("HostConfig.AutoRemove", True),
        ("HostConfig.PublishAllPorts", True),
        ("HostConfig.PortBindings", {"80/tcp": [{"HostPort": "80"}]}),
        ("HostConfig.MaskedPaths", []),
        ("HostConfig.ReadonlyPaths", None),
        ("HostConfig.IpcMode", "none"),
        # nobody listed these, yet a set one is still another container
        ("HostConfig.Devices", [{"PathOnHost": "/dev/kmsg"}]),
        ("HostConfig.Sysctls", {"kernel.shm_rmid_forced": "1"}),
        ("HostConfig.ExtraHosts", ["evil:1.2.3.4"]),
        ("HostConfig.Links", ["other:other"]),
        ("HostConfig.GroupAdd", ["docker"]),
        ("HostConfig.CgroupParent", "/evil"),
        ("HostConfig.NewConfinementKey", "off"),
    ],
)
def test_a_previously_created_container_with_another_configuration_is_refused_untouched(
    tmp_path: Path, field: str, value: object
) -> None:
    """Its labels are all right and it is fresh, which said yes until now: it would have run with this."""
    docker, persisted = FakeDocker(), []
    docker.image_config = {"Healthcheck": {"Test": ["NONE"]}}
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    spec = Spec(work)
    mine = left_by_a_dead_client(backend, docker, spec)
    other = left_by_a_dead_client(backend, docker, Spec(work, owner=make_owner("u" * 32)))
    changed(docker.containers[mine]["record"], field, value)
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, field)
    assert_refused_untouched(docker, persisted, mine, other)
    assert all(other not in call for call in docker.calls), "another container was not even looked at"


@pytest.mark.parametrize(
    "request_change",
    [
        {"argv": ["other"]},
        {"env": {"EXTRA": "1"}},
        {"writable": ()},  # a retry may only ask less: it still gets what it asked, not the writer
        {"readable": ("sibling",)},
        {"network": "full"},
        {"protected": ("work/.git",)},
    ],
    ids=lambda change: next(iter(change)),
)
def test_a_retry_that_asks_for_something_else_never_gets_the_earlier_container(
    tmp_path: Path, request_change: dict[str, Any]
) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted, allow_full_network=True)
    work = work_dir(tmp_path)
    (work / ".git").mkdir()
    (tmp_path / "sibling").mkdir()
    owner = make_owner()
    mine = left_by_a_dead_client(backend, docker, Spec(work, owner=owner))
    docker.calls.clear()
    fields = dict(request_change)
    argv = fields.pop("argv", ["agent"])
    if "readable" in fields:
        fields["readable"] = (tmp_path / "sibling",)
    if "protected" in fields:
        fields["protected"] = (work / ".git",)
    with pytest.raises(CapabilityUnavailable) as caught:
        backend.wrap(argv, Spec(work, owner=owner, **fields))  # type: ignore[attr-defined]
    assert_mismatch(caught.value, mine)
    assert_refused_untouched(docker, persisted, mine)


def test_a_read_only_request_is_never_served_by_the_writer_left_for_its_owner_on_any_daemon(
    tmp_path: Path,
) -> None:
    """Before: a writer on an identity daemon passed the mapping check, so the reader got write access."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    owner = make_owner()
    mine = left_by_a_dead_client(backend, docker, Spec(work, owner=owner))
    docker.calls.clear()
    assert_mismatch(refusal(backend, reader_of(work, owner=owner)), mine, "Mounts", "HostConfig.Mounts")
    assert_refused_untouched(docker, persisted, mine)
    # the daemon's view and the stored request are read apart: either one alone refuses
    spec = reader_of(work, owner=make_owner("r" * 32))
    other = left_by_a_dead_client(backend, docker, spec)
    docker.containers[other]["mounts"][0]["RW"] = True
    assert_mismatch(refusal(backend, spec), other, "Mounts")
    other_host = reader_of(work, owner=make_owner("h" * 32))
    third = left_by_a_dead_client(backend, docker, other_host)
    del docker.containers[third]["record"]["HostConfig"]["Mounts"][0]["ReadOnly"]
    assert_mismatch(refusal(backend, other_host), third, "HostConfig.Mounts")


def test_a_rootless_daemon_refuses_a_mismatch_the_mapping_check_lets_through(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    spec = reader_of(work)
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["Config"]["Cmd"] = ["evil"]
    docker.security_options = '["name=rootless"]'
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, "Config.Cmd")
    assert_refused_untouched(docker, persisted, mine)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("HostConfig.MaskedPaths", ["/proc/asound"]),  # shrunk: non-empty, which alone used to pass
        ("HostConfig.ReadonlyPaths", ["/proc/bus"]),
        ("HostConfig.MaskedPaths", ["/nothing/of/the/sort"]),
        ("HostConfig.MaskedPaths", ["/proc/asound", "/proc/keys", "/more"]),  # exact, not merely at least
        ("HostConfig.IpcMode", "shareable"),  # in the closed set, yet not what this daemon gives
        ("HostConfig.ShmSize", 1 << 40),
        ("HostConfig.LogConfig.Config", {"max-size": "1t"}),
    ],
)
def test_what_only_the_daemon_fills_in_is_compared_with_what_it_fills_in_now(
    tmp_path: Path, field: str, value: object
) -> None:
    """A client of the API can create a container with fewer masked paths, under the owner's labels."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    changed(docker.containers[mine]["record"], field, value)
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, field)
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"
    assert list(docker.containers) == [mine], "the probe is gone"
    assert docker.probe_verbs() == ["create", "inspect", "rm"]
    assert not {"create", "start", "stop", "kill", "rm"} & set(docker.owner_verbs())
    assert "start" not in docker.verbs()


def test_the_order_of_the_protected_paths_confines_nothing(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["HostConfig"]["MaskedPaths"].reverse()
    assert backend.wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]


def test_a_container_of_a_daemon_with_other_defaults_is_refused_after_its_upgrade(tmp_path: Path) -> None:
    """The newer list is the wider one: the container would run without what the daemon now hides."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.masked_paths = [*docker.masked_paths, "/sys/devices/virtual/powercap"]
    assert_mismatch(refusal(backend, spec), mine, "HostConfig.MaskedPaths")
    assert persisted == []


def test_the_baseline_probe_is_this_requests_confinement_and_nothing_of_the_request(tmp_path: Path) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker, allow_full_network=True)
    work = work_dir(tmp_path)
    spec = Spec(work, env={"API_TOKEN": SECRET, "LANG": "C"}, network="full")
    env_file = tmp_path / "env-file"
    env_file.write_text(f"API_TOKEN={SECRET}\n")
    mine = docker(backend.create_argv(["agent"], spec, env_file=env_file)).stdout.strip()  # type: ignore[attr-defined]
    docker.calls.clear()
    assert backend.wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]
    (create,) = [call for call in docker.calls if call[1] == "create"]
    assert is_probe(create)
    request = backend.create_argv(["agent"], spec, env_file=env_file)  # type: ignore[attr-defined]

    def flags(call: Sequence[str]) -> list[str]:
        decisive = ("--user", "--cap-drop", "--security-opt", "--tmpfs", "--pids-limit", "--memory", "--cpus")
        found = [item for flag, item in itertools.pairwise(call) if flag in decisive]
        return [*found, *(item for item in call if item in {"--init", "--read-only"})]

    assert flags(create) == flags(request)
    assert create[create.index("--network") + 1] == "none"
    assert create[create.index("--pull") + 1] == "never"
    assert not {"--mount", "--volume", "--env", "--env-file", "--interactive"} & set(create)
    assert not any(item.startswith("skm.owner_nonce") for item in create)
    assert all(SECRET not in item for call in docker.calls for item in call)
    assert "start" not in docker.verbs()


def probe_answering(docker: FakeDocker, verb: str, answer: DockerResult) -> Callable[..., DockerResult]:
    """The real daemon's work, with ``answer`` as what the client hears on that probe call."""

    def runner(argv: Sequence[str]) -> DockerResult:
        done = docker(argv)
        return answer if is_probe(argv) and argv[1] == verb else done

    return runner


def inspect_of_the_probe(docker: FakeDocker, **changes: object) -> Callable[..., DockerResult]:
    """The real report of the probe with the dotted ``changes``."""

    def runner(argv: Sequence[str]) -> DockerResult:
        done = docker(argv)
        if not (is_probe(argv) and argv[1] == "inspect"):
            return done
        [record] = json.loads(done.stdout)
        for path, value in changes.items():
            changed(record, path.replace("__", "."), value)
        return DockerResult(0, json.dumps([record]))

    return runner


def recovering_through(runner: Callable[..., DockerResult], tmp_path: Path, persisted: list[Any]) -> Any:
    return container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
    )


@pytest.mark.parametrize(
    ("make_runner", "unproven", "removes_probe"),
    [
        (lambda d: probe_answering(d, "create", DockerResult(1, "", "boom")), ["baseline"], True),
        (lambda d: probe_answering(d, "create", DockerResult(0, "not-an-id\n")), ["baseline"], True),
        (lambda d: probe_answering(d, "inspect", DockerResult(1, "", "boom")), ["baseline"], True),
        (lambda d: probe_answering(d, "inspect", DockerResult(0, "[]")), ["baseline"], True),
        (lambda d: probe_answering(d, "rm", DockerResult(1, "", "boom")), ["baseline"], True),
        (lambda d: inspect_of_the_probe(d, Id="e" * 64), ["baseline"], False),
        (lambda d: inspect_of_the_probe(d, Name="/someone-elses"), ["baseline"], False),
        (lambda d: inspect_of_the_probe(d, State__Status="running"), ["baseline"], False),
        (lambda d: inspect_of_the_probe(d, Config__Labels={}), ["baseline"], False),
        (lambda d: inspect_of_the_probe(d, Config__Cmd=["/bin/sh"]), ["baseline"], False),
        (
            lambda d: inspect_of_the_probe(d, HostConfig__MaskedPaths=ABSENT),
            ["baseline:HostConfig.MaskedPaths"],
            True,
        ),
        (
            lambda d: inspect_of_the_probe(d, HostConfig__ReadonlyPaths=[]),
            ["baseline:HostConfig.ReadonlyPaths"],
            True,
        ),
        (
            lambda d: inspect_of_the_probe(d, HostConfig__MaskedPaths="/proc/keys"),
            ["baseline:HostConfig.MaskedPaths"],
            True,
        ),
        (
            lambda d: inspect_of_the_probe(d, HostConfig__ShmSize=ABSENT),
            ["baseline:HostConfig.ShmSize"],
            True,
        ),
    ],
    ids=[
        "create-fails",
        "create-returns-no-id",
        "inspect-fails",
        "inspect-empty",
        "rm-fails",
        "other-id",
        "other-name",
        "started",
        "unlabelled",
        "other-cmd",
        "masked-absent",
        "readonly-empty",
        "masked-malformed",
        "shm-absent",
    ],
)
def test_a_baseline_the_daemon_does_not_prove_refuses_the_recovered_container(
    tmp_path: Path,
    make_runner: Callable[[FakeDocker], Callable[..., DockerResult]],
    unproven: list[str],
    removes_probe: bool,
) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)
    docker.calls.clear()
    error = refusal(recovering_through(make_runner(docker), tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == unproven
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"
    assert not {"create", "start", "stop", "kill", "rm"} & set(docker.owner_verbs())
    assert ("rm" in docker.probe_verbs()) is removes_probe


def test_a_foreign_container_at_the_probe_name_is_never_removed(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)
    foreign = left_by_a_dead_client(
        container_backend(tmp_path, docker), docker, Spec(spec.workdir, owner=make_owner("f" * 32))
    )

    def colliding(argv: Sequence[str]) -> DockerResult:
        if is_probe(argv) and argv[1] == "create":
            name = argv[argv.index("--name") + 1]
            docker.containers[foreign]["record"]["Name"] = f"/{name}"
            docker.calls.append(tuple(argv))
            return DockerResult(125, "", f"Conflict. The container name /{name} is already in use")
        return docker(argv)

    error = refusal(recovering_through(colliding, tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven"
    assert "rm" not in docker.verbs()
    assert {mine, foreign} == set(docker.containers)


def test_a_daemon_with_nothing_to_hide_is_no_baseline_for_a_container_that_hides_something(
    tmp_path: Path,
) -> None:
    """Equal to nothing would be equal to an unconfined default: an empty baseline never vouches."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.masked_paths = []
    error = refusal(backend, spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == ["baseline:HostConfig.MaskedPaths"]
    assert docker.containers[mine]["state"] == "created"


def test_a_daemon_that_changed_during_the_probe_proves_nothing_about_the_recovered_container(
    tmp_path: Path,
) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)

    def runner(argv: Sequence[str]) -> DockerResult:
        done = docker(argv)
        if is_probe(argv) and argv[1] == "rm":
            docker.daemon = "daemon-B"
        return done

    error = refusal(recovering_through(runner, tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == ["baseline"]
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"


def recovered_with_image_volumes(tmp_path: Path) -> tuple[FakeDocker, Spec, str]:
    """A recovered container of an image with volumes, one of them where the probe's own tmpfs is."""
    docker = FakeDocker()
    docker.image_config = {"Volumes": {"/data": {}, "/cache/": {}, "/tmp": {}}}  # noqa: S108
    spec = Spec(work_dir(tmp_path))
    return docker, spec, left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)


def volumes_of_the_probe(calls: Sequence[tuple[str, ...]]) -> list[str]:
    return [call[-1] for call in calls if call[1:3] == ("volume", "inspect")]


def test_the_probe_takes_its_anonymous_volumes_and_only_those(tmp_path: Path) -> None:
    docker, spec, mine = recovered_with_image_volumes(tmp_path)
    # a neighbour of a different owner: its volumes must stay after the probe removes only its own
    neighbour_argv = container_backend(tmp_path, docker).create_argv(  # type: ignore[attr-defined]
        ["agent"], Spec(work_dir(tmp_path), owner=make_owner(uuid4().hex)), env_file=None
    )
    neighbour = docker(neighbour_argv).stdout.strip()
    user_volume = docker(
        [
            "docker",
            "create",
            "--name",
            "user",
            "--user",
            "1:1",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "x",
            "--tmpfs",
            "/tmp:rw",  # noqa: S108
            "--pids-limit",
            "1",
            "--memory",
            "1g",
            "--cpus",
            "1",
            "--network",
            "none",
            "--workdir",
            "/",
            "--mount",
            "type=volume,src=user-data,dst=/data",
            IMAGE,
            "x",
        ]
    ).stdout.strip()
    before = dict(docker.volumes)
    assert "user-data" in before
    docker.calls.clear()
    assert container_backend(tmp_path, docker).wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]
    assert docker.volumes == before, "the daemon has every volume it had, and none of the probe"
    assert {mine, neighbour, user_volume} == set(docker.containers)
    (rm,) = [call for call in docker.calls if call[1] == "rm"]
    assert rm[2] == "--volumes"
    assert is_probe(rm)
    checked = volumes_of_the_probe(docker.calls)
    assert len(checked) == 2, "one per volume of the image, none for the path of its tmpfs"
    assert not set(checked) & set(before)
    assert not [call for call in docker.calls if call[1:3] == ("volume", "rm")], "never removed by itself"


def test_a_probe_removed_without_its_volumes_refuses_and_names_them(tmp_path: Path) -> None:
    """The defect itself: a plain ``rm`` succeeds, and only the question about the volume tells."""
    docker, spec, mine = recovered_with_image_volumes(tmp_path)
    before = set(docker.volumes)
    persisted: list[Any] = []

    def runner(argv: Sequence[str]) -> DockerResult:
        return docker([item for item in argv if item != "--volumes"])

    error = refusal(recovering_through(runner, tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == ["baseline"]
    left = set(error.details["volumes"])  # type: ignore[arg-type]
    assert len(left) == 2
    assert set(docker.volumes) == before | left
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"


def test_a_volume_another_container_took_stays_and_refuses(tmp_path: Path) -> None:
    """Between the inspect and the ``rm`` someone mounts the probe's volume: it is theirs now, the daemon says
    nothing about keeping it, and neither it nor their container is touched."""
    docker, spec, mine = recovered_with_image_volumes(tmp_path)
    persisted: list[Any] = []
    other = "o" * 64
    taken: list[str] = []

    def runner(argv: Sequence[str]) -> DockerResult:
        done = docker(argv)
        if is_probe(argv) and argv[1] == "inspect":
            mounts = json.loads(done.stdout)[0]["Mounts"]
            taken.append(mounts[0]["Name"])
            docker.containers[other] = {"labels": {}, "state": "created", "mounts": mounts[:1]}
        return done

    error = refusal(recovering_through(runner, tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["volumes"] == taken
    assert taken[0] in docker.volumes
    assert other in docker.containers
    assert docker.containers[mine]["state"] == "created"
    assert persisted == []
    assert not [call for call in docker.calls if call[1:3] == ("volume", "rm")]


@pytest.mark.parametrize(
    "answer",
    [
        DockerResult(0, '[{"Name": "x"}]'),
        DockerResult(1, "", "dial unix /var/run/docker.sock: connect: no such file or directory"),
        DockerResult(1, "", "Cannot connect to the Docker daemon"),
        DockerResult(1, "", "Error response from daemon: get " + "f" * 64 + ": no such volume"),
        DockerResult(1, "", "boom"),
        DockerResult(0, "", "no such volume"),
    ],
    ids=["still-there", "transport", "no-daemon", "about-another-volume", "other-error", "exit-zero"],
)
def test_a_volume_not_shown_gone_refuses_the_recovered_container(
    tmp_path: Path, answer: DockerResult
) -> None:
    docker, spec, mine = recovered_with_image_volumes(tmp_path)
    persisted: list[Any] = []

    def runner(argv: Sequence[str]) -> DockerResult:
        done = docker(argv)
        return answer if argv[1] == "volume" else done

    error = refusal(recovering_through(runner, tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == ["baseline"]
    assert len(error.details["volumes"]) == 2  # type: ignore[arg-type]
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"


@pytest.mark.parametrize(
    "docker_mount",
    [
        {"Type": "volume", "Name": "user-data", "Destination": "/data", "Source": "/v/user-data", "RW": True},
        {"Type": "bind", "Name": "a" * 64, "Destination": "/data", "Source": "/", "RW": True},
        {"Type": "volume", "Name": "a" * 64, "Destination": "/elsewhere", "Source": "/v", "RW": True},
        {"Type": "volume", "Destination": "/data", "Source": "/v", "RW": True},
        {"Type": "volume", "Name": 1, "Destination": "/data", "Source": "/v", "RW": True},
        "not a mount",
    ],
    ids=["named", "bind", "undeclared-path", "no-name", "name-of-other-shape", "not-an-object"],
)
def test_a_mount_of_the_probe_nobody_asked_for_refuses_and_removes_nothing_else(
    tmp_path: Path, docker_mount: object
) -> None:
    docker, spec, mine = recovered_with_image_volumes(tmp_path)
    docker.volumes["user-data"] = False
    persisted: list[Any] = []
    report = inspect_of_the_probe(docker, Mounts=[docker_mount])
    error = refusal(recovering_through(report, tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == ["baseline"]
    assert "user-data" in docker.volumes
    assert docker.containers[mine]["state"] == "created"
    assert persisted == []
    assert not [call for call in docker.calls if call[1:3] == ("volume", "rm")]


@pytest.mark.parametrize(
    "changes",
    [
        {"Mounts": []},
        {"Mounts": ABSENT},
        {"Mounts": "none"},
        {"Config__Volumes": ABSENT},
        {"Config__Volumes": ["/data"]},
        {"Config__Volumes": {"/more": {}}},
    ],
    ids=[
        "no-entry",
        "mounts-absent",
        "mounts-malformed",
        "volumes-absent",
        "volumes-malformed",
        "other-path",
    ],
)
def test_a_probe_that_does_not_name_its_volumes_refuses(tmp_path: Path, changes: dict[str, object]) -> None:
    docker, spec, mine = recovered_with_image_volumes(tmp_path)
    persisted: list[Any] = []
    error = refusal(recovering_through(inspect_of_the_probe(docker, **changes), tmp_path, persisted), spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == ["baseline"]
    assert docker.containers[mine]["state"] == "created"
    assert persisted == []


def test_a_daemon_that_changed_after_removing_the_volumes_proves_nothing(tmp_path: Path) -> None:
    """``no such volume`` from another daemon says nothing about this one."""
    docker, spec, mine = recovered_with_image_volumes(tmp_path)
    persisted: list[Any] = []

    def runner(argv: Sequence[str]) -> DockerResult:
        done = docker(argv)
        if argv[1] == "volume":
            docker.daemon = "daemon-B"
        return done

    error = refusal(recovering_through(runner, tmp_path, persisted), spec)
    assert error.details["unproven"] == ["baseline"]
    assert docker.containers[mine]["state"] == "created"
    assert persisted == []


def test_a_probe_that_stayed_is_named_and_is_no_container_of_the_owner(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)

    def runner(argv: Sequence[str]) -> DockerResult:
        if is_probe(argv) and argv[1] == "rm":
            return DockerResult(1, "", "cannot remove")
        return docker(argv)

    stuck = recovering_through(runner, tmp_path, persisted)
    error = refusal(stuck, spec)
    assert error.details["unproven"] == ["baseline"]
    leftover = next(cid for cid in docker.containers if cid != mine)
    assert docker.containers[leftover]["record"]["Name"] == f"/{error.details['probe']}"
    assert docker.containers[leftover]["labels"] == {"skm.confinement_baseline": "true"}
    assert docker.containers[leftover]["state"] == "created"
    found = container_backend(tmp_path, docker).recover(spec.owner)  # type: ignore[attr-defined]
    assert found.container_id == mine, "neither ambiguous nor mistaken for the owner's"
    assert container_backend(tmp_path, docker, persisted=persisted).wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("field", "extra"),
    [
        ("Consistency", "cached"),
        ("BindOptions", {"Propagation": "rshared"}),
        ("VolumeOptions", {"NoCopy": True}),
    ],
)
def test_a_mount_option_nobody_requested_is_another_mount(tmp_path: Path, field: str, extra: object) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["HostConfig"]["Mounts"][0][field] = extra
    assert_mismatch(refusal(backend, spec), mine, "HostConfig.Mounts")
    assert persisted == []


# flags, network, fields that must differ; "{other}" is a directory no request of the tests grants, read-only
# because a writable bind on a remapping daemon is refused by the mapping check before this comparison
FORGED_CREATES: tuple[tuple[tuple[str, ...], str | None, tuple[str, ...]], ...] = (
    (("--entrypoint", "/bin/forged-entrypoint"), None, ("Config.Entrypoint", "Path")),
    (("--privileged",), None, ("HostConfig.Privileged",)),
    (("--cap-add", "SYS_ADMIN"), None, ("HostConfig.CapAdd",)),
    (("--pid", "host"), None, ("HostConfig.PidMode",)),
    (("--ipc", "host"), None, ("HostConfig.IpcMode",)),
    (("--security-opt", "seccomp=unconfined"), None, ("HostConfig.SecurityOpt",)),
    (
        ("--security-opt", "systempaths=unconfined"),
        None,
        ("HostConfig.MaskedPaths", "HostConfig.ReadonlyPaths"),
    ),
    (("--env", "LD_PRELOAD=/evil.so"), None, ("Config.Env",)),
    (("--mount", "type=bind,src={other},dst=/extra,readonly"), None, ("Mounts", "HostConfig.Mounts")),
    (("--volume", "{other}:/extra:ro"), None, ("Mounts", "HostConfig.Binds")),
    (("--add-host", "evil:192.0.2.1"), None, ("HostConfig.ExtraHosts",)),
    ((), "bridge", ("HostConfig.NetworkMode", "NetworkSettings.Networks")),
)


@pytest.mark.parametrize(("flags", "network", "fields"), FORGED_CREATES, ids=str)
def test_a_create_with_the_owners_labels_and_other_flags_is_refused_untouched(
    tmp_path: Path, flags: tuple[str, ...], network: str | None, fields: tuple[str, ...]
) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    spec = reader_of(work)
    named = [flag.format(other=tmp_path) for flag in flags]
    create = create_with(docker, *named, network=network)
    mine = create(backend.create_argv(["agent"], spec, env_file=None)).stdout.strip()  # type: ignore[attr-defined]
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, *fields)
    assert_refused_untouched(docker, persisted, mine)


def test_a_mount_the_request_does_not_have_is_refused_in_the_daemons_view(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    for extra in (
        {"Type": "bind", "Source": "/", "Destination": "/host", "RW": False},
        {
            "Type": "volume",
            "Source": "/var/lib/docker/volumes/x",
            "Destination": "/not-of-the-image",
            "RW": True,
        },
        {"Type": "tmpfs", "Source": "", "Destination": "/scratch", "RW": True},
    ):
        owner = make_owner(uuid4().hex)
        current = Spec(spec.workdir, owner=owner)
        mine = left_by_a_dead_client(backend, docker, current)
        docker.containers[mine]["mounts"].append(extra)
        assert_mismatch(refusal(backend, current), mine, "Mounts")
    assert persisted == []


@pytest.mark.parametrize(
    "field",
    [
        "Image",
        "Path",
        "Args",
        "Config.Image",
        "Config.Cmd",
        "Config.Entrypoint",
        "Config.Env",
        "Config.User",
        "Config.WorkingDir",
        "Config.Volumes",
        "Config.OpenStdin",
        "Config.Tty",
        "NetworkSettings.Networks",
        "NetworkSettings",
        "HostConfig.NetworkMode",
        "HostConfig.Init",
        "HostConfig.Privileged",
        "HostConfig.ReadonlyRootfs",
        "HostConfig.CapDrop",
        "HostConfig.CapAdd",
        "HostConfig.SecurityOpt",
        "HostConfig.Tmpfs",
        "HostConfig.Binds",
        "HostConfig.VolumesFrom",
        "HostConfig.Memory",
        "HostConfig.MemorySwap",
        "HostConfig.NanoCpus",
        "HostConfig.PidsLimit",
        "HostConfig.PidMode",
        "HostConfig.UTSMode",
        "HostConfig.UsernsMode",
        "HostConfig.IpcMode",
        "HostConfig.CgroupnsMode",
        "HostConfig.Runtime",
        "HostConfig.LogConfig",
        "HostConfig.RestartPolicy",
        "HostConfig.AutoRemove",
        "HostConfig.PublishAllPorts",
        "HostConfig.PortBindings",
        "HostConfig.MaskedPaths",
        "HostConfig.ReadonlyPaths",
        "HostConfig",
    ],
)
def test_metadata_the_daemon_omits_proves_nothing(tmp_path: Path, field: str) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    changed(docker.containers[mine]["record"], field, ABSENT)
    docker.calls.clear()
    error = refusal(backend, spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert field in str(error.details["unproven"]), error.details
    assert_refused_untouched(docker, persisted, mine)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Path", 1),
        ("Args", "agent"),
        ("Config.Cmd", "agent"),
        ("Config.Cmd", [1]),
        ("Config.Env", {"HOME": "/home/skm"}),
        ("Config.Env", [None]),
        ("Config.User", 1000),
        ("Config.Volumes", ["/data"]),
        ("Config.Healthcheck", "none"),
        ("Config.OpenStdin", 0),  # ``False == 0`` must not pass for a flag
        ("HostConfig.Privileged", 0),
        ("HostConfig.Privileged", "false"),
        ("HostConfig.Memory", "4g"),
        ("HostConfig.PidsLimit", True),
        ("HostConfig.Mounts", "bind"),
        ("HostConfig.Mounts", [1]),
        ("HostConfig.Mounts", [{"Type": "bind"}]),
        ("HostConfig.Mounts", [{"Type": "bind", "Source": "/a", "Target": "/b", "ReadOnly": "yes"}]),
        ("NetworkSettings.Networks", None),
        ("NetworkSettings.Networks", ["none"]),
        ("HostConfig", "none"),
        ("Config", None),
    ],
)
def test_malformed_metadata_proves_nothing(tmp_path: Path, field: str, value: object) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    changed(docker.containers[mine]["record"], field, value)
    if field == "Config":  # the labels are rendered into it: this one is a broken answer as a whole
        docker.containers[mine]["report"] = json.dumps([docker.containers[mine]["record"]])
    docker.calls.clear()
    error = refusal(backend, spec)
    assert error.details["reason"] in {"recovered_config_unproven", "owner_mismatch"}, error.details
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"
    assert not {"create", "start", "stop", "kill", "rm"} & set(docker.verbs())


@pytest.mark.parametrize(
    "mounts",
    [
        "null",
        "[1]",
        '[{"Type": "bind"}]',
        '[{"Type": "bind", "Source": "/a", "Destination": "/b"}]',
        '[{"Type": "bind", "Source": "/a", "Destination": "/b", "RW": "no"}]',
        "not json",
    ],
)
def test_a_daemon_view_of_the_mounts_that_says_nothing_refuses_on_an_identity_daemon_too(
    tmp_path: Path, mounts: str
) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["mounts_report"] = mounts
    docker.calls.clear()
    error = refusal(backend, spec)
    assert error.details["reason"] == "recovered_config_unproven", error.details
    assert error.details["unproven"] == ["Mounts"]
    assert_refused_untouched(docker, persisted, mine)


@pytest.mark.parametrize("report", ["", "not json", "null", "{}", "[]", "[1]", "[{}, {}]", "[{}]"])
def test_an_inspect_answer_that_is_not_the_one_container_is_no_owner(tmp_path: Path, report: str) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["report"] = report
    docker.calls.clear()
    assert refusal(backend, spec).details["reason"] == "owner_mismatch"
    assert_refused_untouched(docker, persisted, mine)


@pytest.mark.parametrize(
    ("field", "value"),
    [("Id", "e" * 64), ("Id", None), ("Name", "/skm-step-other"), ("Name", None)],
)
def test_labels_alone_do_not_make_an_owner(tmp_path: Path, field: str, value: object) -> None:
    """Whoever reaches the daemon can write labels; its names are unique and the ID is what gets started."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"][field] = value
    docker.calls.clear()
    assert refusal(backend, spec).details["reason"] == "owner_mismatch"
    assert_refused_untouched(docker, persisted, mine)


def test_recover_itself_refuses_what_only_the_labels_call_the_owners(tmp_path: Path) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["Name"] = "/someone-elses"
    with pytest.raises(CapabilityUnavailable) as caught:
        backend.recover(spec.owner)  # type: ignore[attr-defined]
    assert caught.value.details["reason"] == "owner_mismatch"


@pytest.mark.parametrize("listed", ["--format=evil", "abc", "A" * 64, "e" * 63, "e" * 64 + " x"])
def test_a_listed_id_that_is_no_container_id_never_reaches_the_daemon(tmp_path: Path, listed: str) -> None:
    docker = FakeDocker()

    def runner(argv: Sequence[str]) -> DockerResult:
        return DockerResult(0, listed + "\n") if argv[1] == "ps" else docker(argv)

    backend = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=lambda created: None,
        home=tmp_path / "home",
    )
    assert refusal(backend, Spec(work_dir(tmp_path))).details["reason"] == "owner_mismatch"
    assert not any(listed in call for call in docker.calls)
    assert "create" not in docker.verbs()


def test_a_container_removed_between_the_list_and_the_inspect_is_not_created_again(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    gone = "e" * 64

    def runner(argv: Sequence[str]) -> DockerResult:
        return DockerResult(0, gone + "\n") if argv[1] == "ps" else docker(argv)

    backend = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
    )
    assert refusal(backend, spec).details["reason"] == "owner_mismatch"
    assert persisted == []
    assert not {"create", "start"} & set(docker.verbs())


def test_a_create_that_lost_the_race_to_another_configuration_does_not_adopt_it(tmp_path: Path) -> None:
    """``_created`` answered with whatever the nonce found: state, mapping, configuration went unchecked."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    owner = make_owner()
    spec = Spec(work, owner=owner)
    raced: list[str] = []

    def runner(argv: Sequence[str]) -> DockerResult:
        if argv[1] != "create":
            return docker(argv)
        raced.append(docker(backend.create_argv(["other"], spec, env_file=None)).stdout.strip())  # type: ignore[attr-defined]
        return DockerResult(125, "", "Conflict. The container name is already in use")

    racing = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
        env_dir=tmp_path,
    )
    assert_mismatch(refusal(racing, spec), raced[0], "Config.Cmd", "Path")
    assert persisted == []
    assert docker.containers[raced[0]]["state"] == "created"
    assert not {"start", "stop", "kill", "rm"} & set(docker.verbs())


def test_a_create_that_lost_the_race_to_a_started_container_does_not_start_it_again(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    work = work_dir(tmp_path)
    spec = Spec(work)
    probe = container_backend(tmp_path, docker)

    def runner(argv: Sequence[str]) -> DockerResult:
        if argv[1] != "create":
            return docker(argv)
        winner = docker(probe.create_argv(["agent"], spec, env_file=None)).stdout.strip()  # type: ignore[attr-defined]
        docker.containers[winner]["state"] = "running"
        return DockerResult(125, "", "Conflict. The container name is already in use")

    racing = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
    )
    assert refusal(racing, spec).details["reason"] == "owner_container_not_fresh"
    assert persisted == []


def test_a_create_that_lost_the_race_to_the_same_request_shares_that_container(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    winner = container_backend(tmp_path, docker)

    def runner(argv: Sequence[str]) -> DockerResult:
        if argv[1] == "create" and not is_probe(argv):
            docker(winner.create_argv(["agent"], spec, env_file=None))  # type: ignore[attr-defined]
            return DockerResult(125, "", "Conflict. The container name is already in use")
        return docker(argv)

    racing = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
    )
    wrapped = racing.wrap(["agent"], spec)  # type: ignore[arg-type]
    assert [created.container_id for created in persisted] == [wrapped.argv[-1]]
    assert list(docker.containers) == [wrapped.argv[-1]]


def test_a_foreign_container_holding_the_name_is_not_touched_or_adopted(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    foreign = "d" * 64
    docker.containers[foreign] = {"labels": {"skm.owner_nonce": "someone-else"}, "state": "running"}

    def runner(argv: Sequence[str]) -> DockerResult:
        if argv[1] == "create":
            docker.calls.append(tuple(argv))
            return DockerResult(125, "", f"Conflict. The container name is in use by {foreign}")
        return docker(argv)

    racing = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
    )
    assert refusal(racing, spec).details["reason"] == "create_failed"
    assert persisted == []
    assert docker.containers[foreign]["state"] == "running"
    assert not {"stop", "kill", "rm", "start"} & set(docker.verbs())
    assert all(foreign not in call for call in docker.calls)


@pytest.mark.parametrize(
    "info",
    [
        "",
        "not json",
        "null",
        "[]",
        '{"DefaultRuntime": "runc"}',
        '{"DefaultRuntime": 1, "LoggingDriver": "json-file", "SwapLimit": true, "CgroupVersion": "2"}',
        '{"DefaultRuntime": "runc", "LoggingDriver": "json-file", "SwapLimit": "yes", "CgroupVersion": "2"}',
    ],
)
def test_what_the_daemon_does_not_say_about_its_defaults_refuses_the_recovery(
    tmp_path: Path, info: str
) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)

    def runner(argv: Sequence[str]) -> DockerResult:
        return DockerResult(0, info) if argv[-1] == "{{json .}}" else docker(argv)

    answering = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
    )
    error = refusal(answering, spec)
    assert error.details["reason"] == "recovered_config_unproven"
    assert error.details["unproven"] == ["daemon"]
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"


@pytest.mark.parametrize(
    "answer",
    [
        DockerResult(1, "", "Error: No such image"),
        DockerResult(0, ""),
        DockerResult(0, "not json"),
        DockerResult(0, "[]"),
        DockerResult(0, '[{"Id": "sha256:1"}]'),
        DockerResult(0, '[{"Id": "sha256:1", "Config": null}]'),
        DockerResult(0, '[{"Config": {}}]'),
        DockerResult(0, '[{"Id": 1, "Config": {}}]'),
        DockerResult(0, '[{"Id": "sha256:1", "Config": {"Env": "A=1"}}]'),
        DockerResult(0, '[{"Id": "sha256:1", "Config": {"Entrypoint": [1]}}]'),
        DockerResult(0, '[{"Id": "sha256:1", "Config": {"Labels": []}}]'),
    ],
    ids=str,
)
def test_an_image_that_cannot_be_inspected_refuses_the_recovery(tmp_path: Path, answer: DockerResult) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)

    def runner(argv: Sequence[str]) -> DockerResult:
        return answer if argv[1] == "image" else docker(argv)

    answering = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=runner,
        persist=persisted.append,
        home=tmp_path / "home",
    )
    error = refusal(answering, spec)
    assert error.details["reason"] == "recovered_config_unproven"
    assert error.details["unproven"] == ["image"]
    assert persisted == []
    assert docker.containers[mine]["state"] == "created"


def test_an_image_that_moved_since_the_create_does_not_run_under_the_old_container(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.image_id = "sha256:" + "5" * 64
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, "Image")
    assert_refused_untouched(docker, persisted, mine)


def test_a_container_of_another_image_digest_is_refused_for_this_setting(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    other = "registry.example/skm-cli@sha256:" + "b" * 64
    docker.containers[mine]["record"]["Config"]["Image"] = other
    docker.calls.clear()
    assert_mismatch(refusal(backend, spec), mine, "Config.Image")
    assert_refused_untouched(docker, persisted, mine)


@pytest.mark.parametrize(
    ("settings", "field"),
    [
        ({"memory": "2g"}, "HostConfig.Memory"),
        ({"cpus": 1.5}, "HostConfig.NanoCpus"),
        ({"pids_limit": 64}, "HostConfig.PidsLimit"),
        ({"tmp_size": "2g"}, "HostConfig.Tmpfs"),
    ],
    ids=["memory", "cpus", "pids", "tmp"],
)
def test_limits_changed_since_the_create_refuse_the_old_container(
    tmp_path: Path, settings: dict[str, Any], field: str
) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)
    assert_mismatch(
        refusal(container_backend(tmp_path, docker, persisted=persisted, **settings), spec), mine, field
    )
    assert persisted == []


def test_the_user_of_the_worker_is_compared_as_the_create_gave_it(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)
    other = container_isolation(
        ContainerSettings(image=IMAGE, uid=2000, gid=2000),
        runner=docker,
        persist=persisted.append,
        home=tmp_path / "home",
    )
    assert_mismatch(refusal(other, spec), mine, "Config.User")
    assert persisted == []


def test_a_daemon_without_swap_limits_keeps_the_swap_it_reports(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    docker.info["SwapLimit"] = False
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    assert docker.containers[mine]["record"]["HostConfig"]["MemorySwap"] == -1
    assert backend.wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]
    docker.info["SwapLimit"] = True
    assert_mismatch(refusal(backend, spec), mine, "HostConfig.MemorySwap")


def test_only_a_cgroup_v1_daemon_may_keep_the_host_cgroup_namespace(tmp_path: Path) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["HostConfig"]["CgroupnsMode"] = "host"
    assert_mismatch(refusal(backend, spec), mine, "HostConfig.CgroupnsMode")
    docker.info["CgroupVersion"] = "1"
    assert backend.wrap(["agent"], spec).argv[-1] == mine  # type: ignore[attr-defined]


def test_interactive_is_part_of_what_was_created(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(container_backend(tmp_path, docker), docker, spec)
    interactive = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=docker,
        persist=persisted.append,
        home=tmp_path / "home",
        interactive=True,
    )
    assert_mismatch(refusal(interactive, spec), mine, "Config.OpenStdin")


def test_a_request_that_is_refused_on_its_own_is_refused_on_recovery_too(tmp_path: Path) -> None:
    """Recovery skipped ``create_argv``, and with it every check of the request itself."""
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    work = work_dir(tmp_path)
    owner = make_owner()
    left_by_a_dead_client(backend, docker, Spec(work, owner=owner))
    home = tmp_path / "home"
    home.mkdir()
    for fields, reason in (
        ({"readable": (home,)}, "forbidden_mount"),
        ({"env": {"BAD NAME": "x"}}, "env_invalid"),
        ({"env": {"LINE": "a\nb"}}, "env_invalid"),
        ({"network": "full"}, "network_full_not_enabled"),
    ):
        assert refusal(backend, Spec(work, owner=owner, **fields)).details["reason"] == reason


SECRET = "s3cret-value-that-must-stay-home"


def test_a_recovered_container_compares_secret_values_and_never_reports_or_passes_them(
    tmp_path: Path,
) -> None:
    """The dead client's create went through the 0600 env file: the value is in the daemon, in no argv."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    work = work_dir(tmp_path)
    owner = make_owner()
    spec = Spec(work, owner=owner, env={"API_TOKEN": SECRET, "LANG": "C"})
    docker.client_dead_after_create = True
    wrapped = backend.wrap(["agent"], spec)  # type: ignore[attr-defined]
    [created] = persisted
    assert wrapped.argv[-1] == created.container_id
    docker.client_dead_after_create = False
    assert docker.env_files == [(0o600, f"API_TOKEN={SECRET}\n")]
    assert f"API_TOKEN={SECRET}" in docker.containers[created.container_id]["record"]["Config"]["Env"]
    # a later retry proves the same secret again, and only by comparing it
    docker.calls.clear()
    assert backend.wrap(["agent"], spec).argv[-1] == created.container_id  # type: ignore[attr-defined]
    assert "create" not in docker.owner_verbs()
    assert not list(tmp_path.glob("skm-env-*")), "no env file was written or left for the comparison"
    assert all(SECRET not in item for call in docker.calls for item in call)

    other = Spec(work, owner=owner, env={"API_TOKEN": "another-" + SECRET, "LANG": "C"})
    error = refusal(backend, other)
    assert_mismatch(error, created.container_id, "Config.Env")
    assert SECRET not in str(error)
    assert SECRET not in json.dumps(dict(error.details))
    assert all(SECRET not in item for call in docker.calls for item in call)


def test_a_malformed_environment_is_refused_without_repeating_it(tmp_path: Path) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    spec = Spec(work_dir(tmp_path), env={"LANG": "C"})
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["Config"]["Env"] = [SECRET, 1]
    error = refusal(backend, spec)
    assert error.details["reason"] == "recovered_config_unproven"
    assert SECRET not in str(error)
    assert SECRET not in json.dumps(dict(error.details))


def test_a_refused_container_can_still_be_found_and_cleaned_by_its_owner(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    mine = left_by_a_dead_client(backend, docker, spec)
    docker.containers[mine]["record"]["HostConfig"]["Privileged"] = True
    assert_mismatch(refusal(backend, spec), mine, "HostConfig.Privileged")
    found = backend.recover(spec.owner)  # type: ignore[attr-defined]
    assert found.container_id == mine
    assert backend.stop(found).state == "removed"  # type: ignore[attr-defined]
    assert mine not in docker.containers
    # and only then does the owner get a fresh one, for what it asks now
    wrapped = backend.wrap(["agent"], spec)  # type: ignore[attr-defined]
    assert docker.containers[wrapped.argv[-1]]["record"]["HostConfig"]["Privileged"] is False
    assert docker.verbs().count("create") == 2


def test_state_mounts_and_configuration_are_decided_on_one_inspect_snapshot(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    left_by_a_dead_client(backend, docker, spec)
    docker.calls.clear()
    backend.wrap(["agent"], spec)  # type: ignore[attr-defined]
    inspects = [call for call in docker.calls if call[1] == "inspect" and not is_probe(call)]
    assert inspects == [("docker", "inspect", "--type", "container", persisted[0].container_id)]


def test_full_network_needs_the_explicit_key_and_allowlist_needs_boundary_and_network(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    off = container_backend(tmp_path, FakeDocker())
    assert refusal(off, Spec(work, network="full")).details["reason"] == "network_full_not_enabled"
    on = container_backend(tmp_path, FakeDocker(), allow_full_network=True)
    assert "--network bridge" in " ".join(on.create_argv(["a"], Spec(work, network="full"), env_file=None))  # type: ignore[attr-defined]
    allow = Spec(work, network="allowlist", network_hosts=("api.example.com",))
    # a named docker network (or a proxy variable) is no proof of an egress boundary
    named = container_backend(tmp_path, FakeDocker(), network="egress-net")
    assert refusal(named, allow).details["missing"] == ["network_allowlist"]
    boundary = proving("egress-proxy", (P.NETWORK_ALLOWLIST,), make_launcher(tmp_path))
    without_network = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=FakeDocker(),
        persist=lambda created: None,
        companions=(boundary,),
        home=tmp_path / "home",
    )
    assert refusal(without_network, allow).details["reason"] == "network_allowlist_unavailable"


def egress_container(tmp_path: Path, docker: FakeDocker, companion: Companion, network: str = "egress-net"):
    return container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000, network=network),
        runner=docker,
        persist=lambda created: None,
        companions=(companion,),
        home=tmp_path / "home",
        env_dir=tmp_path,
    )


def test_container_allowlist_needs_an_egress_proof_bound_to_hosts_image_and_network(tmp_path: Path) -> None:
    work = work_dir(tmp_path)
    launcher = make_launcher(tmp_path)
    allow = Spec(work, network="allowlist", network_hosts=("api.example.com",))
    asked: list[ProofRequest] = []
    docker = FakeDocker()
    boundary = proving("egress-proxy", (P.NETWORK_ALLOWLIST,), launcher, asked=asked)
    wrapped = egress_container(tmp_path, docker, boundary).wrap(["agent"], allow)  # type: ignore[attr-defined]
    assert wrapped.argv[0] == launcher  # the egress launcher starts the docker client
    assert wrapped.argv[1:3] == ("docker", "start")
    (request,) = asked
    assert request.context == {"image": IMAGE, "network": "egress-net", "allow_full_network": "False"}
    assert request.binding == request_binding("container", allow, ["agent"], request.context)  # type: ignore[arg-type]
    # a proof earned for another docker network, command or host list does not carry over
    elsewhere = request_binding("container", allow, ["agent"], {**request.context, "network": "other-net"})  # type: ignore[arg-type]
    for forged in (elsewhere, "f" * 64):
        docker = FakeDocker()
        refused = refusal(
            egress_container(
                tmp_path, docker, proving("egress-proxy", (P.NETWORK_ALLOWLIST,), launcher, binding=forged)
            ),
            allow,
        )
        assert refused.details["reason"] == "companion_proof_unbound"
        assert "create" not in docker.verbs()  # nothing was created, let alone started


def test_disk_quota_is_not_claimed_by_bind_mounts(tmp_path: Path) -> None:
    isolation = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=FakeDocker(),
        persist=lambda created: None,
        require=(P.DISK_QUOTA,),
        home=tmp_path / "home",
    )
    assert refusal(isolation, Spec(work_dir(tmp_path))).details["missing"] == ["disk_quota"]


def test_without_a_persist_hook_the_lifecycle_is_unproven(tmp_path: Path) -> None:
    docker = FakeDocker()
    error = refusal(container_backend(tmp_path, docker, persist=False), Spec(work_dir(tmp_path)))
    assert error.details["missing"] == ["lifecycle"]
    assert "create" not in docker.verbs(), "refused before anything was created"


# -- container: lifecycle --------------------------------------------------------------------------


def test_wrap_creates_persists_the_id_and_daemon_before_returning_a_start_argv(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    work = work_dir(tmp_path)
    spec = Spec(work)
    wrapped = container_backend(tmp_path, docker, persisted=persisted).wrap(["agent"], spec)  # type: ignore[attr-defined]
    assert docker.verbs().count("create") == 1
    assert "start" not in docker.verbs(), "the adapter never starts: the runner executes the returned argv"
    [created] = persisted
    assert wrapped.argv == ("docker", "start", "--attach", created.container_id)
    assert wrapped.ownership == ProcessOwnership(
        owner=spec.owner, kind="container", ref=created.container_id, daemon_identity="daemon-A"
    )
    assert created.name == f"skm-step-{spec.owner.unit_id}"
    assert wrapped.cwd == work


def test_failing_persist_stops_the_unstarted_container_and_propagates(tmp_path: Path) -> None:
    docker = FakeDocker()

    def persist(created: CreatedContainer) -> None:
        raise OSError("marker disk full")

    isolation = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=docker,
        persist=persist,
        home=tmp_path / "h",
    )
    with pytest.raises(OSError, match="marker disk full"):
        isolation.wrap(["agent"], Spec(work_dir(tmp_path)))  # type: ignore[arg-type]
    assert "start" not in docker.verbs()
    assert {"stop", "kill", "rm"} <= set(docker.verbs()), "cleaned up by ID after the failed persist"


def test_a_client_killed_after_create_recovers_by_labels_without_a_second_create(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    spec = Spec(work_dir(tmp_path))
    docker.client_dead_after_create = True
    wrapped = backend.wrap(["agent"], spec)  # type: ignore[attr-defined]
    assert docker.owner_verbs().count("create") == 1
    [created] = persisted
    assert wrapped.ownership.ref == created.container_id
    # a retry of the same owner reuses the container instead of creating another one
    again = backend.wrap(["agent"], spec)  # type: ignore[attr-defined]
    assert docker.owner_verbs().count("create") == 1
    assert again.ownership.ref == created.container_id


def test_a_container_that_already_ran_for_this_owner_is_never_started_again(tmp_path: Path) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    spec = Spec(work_dir(tmp_path))
    backend.wrap(["agent"], spec)  # type: ignore[attr-defined]
    for data in docker.containers.values():
        data["state"] = "exited"
    assert refusal(backend, spec).details["reason"] == "owner_container_not_fresh"
    assert docker.verbs().count("create") == 1


def test_ambiguous_or_foreign_labels_stop_the_recovery(tmp_path: Path) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    spec = Spec(work_dir(tmp_path))
    backend.wrap(["agent"], spec)  # type: ignore[attr-defined]
    [(container_id, data)] = docker.containers.items()
    docker.containers["f" * 64] = {"labels": dict(data["labels"]), "state": "created"}
    assert refusal(backend, spec).details["reason"] == "owner_ambiguous"
    del docker.containers["f" * 64]
    data["labels"]["skm.attempt"] = str(uuid4())
    assert refusal(backend, spec).details["reason"] == "owner_mismatch"
    assert container_id in docker.containers


def test_stop_kills_by_id_and_removes_only_after_confirming_the_state(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    backend.wrap(["agent"], Spec(work_dir(tmp_path)))  # type: ignore[attr-defined]
    [created] = persisted
    docker.containers[created.container_id]["state"] = "running"
    docker.calls.clear()
    result = backend.stop(created)  # type: ignore[attr-defined]  # the client process is long gone: the ID is enough
    assert (result.confirmed, result.state) == (True, "removed")
    verbs = docker.verbs()
    assert verbs.index("stop") < verbs.index("kill") < verbs.index("rm")
    assert all(call[-1] == created.container_id for call in docker.calls if call[1] in {"stop", "kill", "rm"})
    assert not any("--rm" in call for call in docker.calls)


def test_unreachable_daemon_leaves_the_cleanup_unconfirmed(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    backend.wrap(["agent"], Spec(work_dir(tmp_path)))  # type: ignore[attr-defined]
    [created] = persisted
    docker.daemon = None
    result = backend.stop(created)  # type: ignore[attr-defined]
    assert (result.confirmed, result.state) == (False, "unconfirmed")
    assert created.container_id in docker.containers, "nothing was claimed removed"


TRANSPORT_ERROR = "dial unix /var/run/docker.sock: connect: no such file or directory"


class VanishingDaemon:
    """Answers ``info`` with the identity, then every other call with a transport error."""

    def __init__(self, inner: FakeDocker, *, vanish_after: str | None = None) -> None:
        self.inner = inner
        self.vanish_after = vanish_after
        self.vanished = vanish_after is None
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str]) -> DockerResult:
        call = tuple(argv)
        self.calls.append(call)
        if self.vanished and call[1] != "info":
            return DockerResult(1, "", TRANSPORT_ERROR)
        if self.vanished and call[1] == "info":
            return DockerResult(0, "daemon-A\n")
        result = self.inner(argv)
        if call[1] == self.vanish_after:
            self.vanished = True
        return result


def test_a_vanished_daemon_socket_is_not_a_removed_container(tmp_path: Path) -> None:
    """F6: "...connect: no such file or directory" is a transport failure, never a confirmed removal."""
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    backend.wrap(["agent"], Spec(work_dir(tmp_path)))  # type: ignore[attr-defined]
    [created] = persisted
    docker.containers[created.container_id]["state"] = "running"
    for after in (None, "kill", "rm"):
        flaky = VanishingDaemon(docker, vanish_after=after)
        backend = container_isolation(
            ContainerSettings(image=IMAGE, uid=1000, gid=1000),
            runner=flaky,
            persist=persisted.append,
            home=tmp_path / "home",
        )
        result = backend.stop(created)  # type: ignore[attr-defined]
        assert (result.confirmed, result.state) != (True, "removed"), after
        if after is None:
            assert (result.confirmed, result.state) == (False, "unconfirmed")
        assert created.container_id in docker.containers or after == "rm"


def test_removal_is_confirmed_only_by_the_creating_daemon_naming_this_container(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    backend.wrap(["agent"], Spec(work_dir(tmp_path)))  # type: ignore[attr-defined]
    [created] = persisted
    other = "e" * 64

    def absent(stderr: str, *, identity: str = "daemon-A") -> bool:
        def runner(argv: Sequence[str]) -> DockerResult:
            if argv[1] == "info":
                return DockerResult(0, identity + "\n")
            return DockerResult(1, "", stderr)

        probe = container_isolation(
            ContainerSettings(image=IMAGE, uid=1000, gid=1000), runner=runner, home=tmp_path / "home"
        )
        return probe._confirmed_absent(created)  # type: ignore[attr-defined]

    assert absent(f"Error: No such object: {created.container_id}")
    assert absent(f"Error response from daemon: No such container: {created.container_id}")
    assert not absent(TRANSPORT_ERROR)
    assert not absent(f"Error: No such object: {other}"), "another container's absence proves nothing"
    assert not absent("Error: No such object: ")
    assert not absent(f"Error: No such object: {created.container_id}", identity="daemon-B")


def test_a_different_daemon_is_not_asked_to_stop_foreign_containers(tmp_path: Path) -> None:
    docker, persisted = FakeDocker(), []
    backend = container_backend(tmp_path, docker, persisted=persisted)
    backend.wrap(["agent"], Spec(work_dir(tmp_path)))  # type: ignore[attr-defined]
    [created] = persisted
    docker.daemon = "daemon-B"
    docker.calls.clear()
    result = backend.stop(created)  # type: ignore[attr-defined]
    assert result.confirmed is False
    assert not {"stop", "kill", "rm"} & set(docker.verbs())


def test_missing_docker_binary_or_daemon_is_unavailable_before_any_create(tmp_path: Path) -> None:
    def no_binary(argv: Sequence[str]) -> DockerResult:
        raise FileNotFoundError(argv[0])

    isolation = container_isolation(
        ContainerSettings(image=IMAGE, uid=1000, gid=1000),
        runner=no_binary,
        persist=lambda created: None,
        home=tmp_path / "home",
    )
    assert isolation.available(None)["available"] is False  # type: ignore[arg-type]
    assert refusal(isolation, Spec(work_dir(tmp_path))).details["reason"] == "daemon_unavailable"
    down = FakeDocker()
    down.daemon = None
    assert refusal(container_backend(tmp_path, down), Spec(work_dir(tmp_path))).details["reason"] == (
        "daemon_unavailable"
    )
    assert "create" not in down.verbs()


def test_missing_image_makes_the_profile_unavailable(tmp_path: Path) -> None:
    docker = FakeDocker()
    other = container_isolation(
        ContainerSettings(image="registry.example/other@sha256:" + "b" * 64, uid=1000, gid=1000),
        runner=docker,
        home=tmp_path / "home",
    )
    status = other.available(None)  # type: ignore[arg-type]
    assert status["available"] is False
    assert "not available" in str(status["reason"])
    assert container_backend(tmp_path, docker).available(None)["available"] is True  # type: ignore[attr-defined]


# -- live canary (needs Docker and a pinned image) -------------------------------------------------

DOCKER_CLIENT_ENV = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "XDG_RUNTIME_DIR")
REPOSITORY = Path(__file__).resolve().parents[2]
CANARY = "test_live_container_hides_host_secrets_blocks_outside_writes_and_has_no_network"


def captured_host_env(config: pytest.Config) -> dict[str, str]:
    """Read host environment variables saved before ``tests/conftest.py`` scrubbed ``os.environ``."""
    saved: dict[str, str] = {}
    workerinput = getattr(config, "workerinput", None)
    xdist_controls = workerinput.get("skm_controls") if isinstance(workerinput, dict) else None
    if isinstance(xdist_controls, dict):
        if xdist_controls.get("host_home"):
            saved["HOME"] = str(xdist_controls["host_home"])
        if xdist_controls.get("container_image"):
            saved["SKM_TEST_CONTAINER_IMAGE"] = str(xdist_controls["container_image"])
    stack = getattr(config, "_cleanup_stack", None)
    for _, callback in getattr(stack, "_exit_callbacks", ()):
        for cell in getattr(callback, "__closure__", None) or ():
            patch = getattr(cell.cell_contents, "__self__", None)
            for item in getattr(patch, "_setitem", ()):
                if (
                    isinstance(item, tuple)
                    and len(item) == 3
                    and isinstance(item[1], str)
                    and isinstance(item[2], str)
                ):
                    saved.setdefault(item[1], item[2])
    return saved


def runnable_layer_tar() -> bytes:
    """Build a minimal rootfs layer tar containing ``sh``, ``ls``, ``cat``, ``true``, ``false`` and libs."""
    buf = io.BytesIO()
    seen: set[str] = set()
    ldd = shutil.which("ldd") or "/usr/bin/ldd"
    with tarfile.open(fileobj=buf, mode="w") as stream:

        def add_dir(path: str, mode: int = 0o755) -> None:
            if not path or path in seen:
                return
            add_dir(os.path.dirname(path))
            seen.add(path)
            info = tarfile.TarInfo(path)
            info.type = tarfile.DIRTYPE
            info.mode = mode
            stream.addfile(info)

        def add_file(target: str, source: Path, mode: int) -> None:
            key = target.lstrip("/")
            if key in seen or not source.exists():
                return
            add_dir(os.path.dirname(key))
            seen.add(key)
            data = source.read_bytes()
            info = tarfile.TarInfo(key)
            info.size = len(data)
            info.mode = mode
            stream.addfile(info, io.BytesIO(data))

        # One entry per path: Docker's containerd image store refuses an archive with duplicate paths.
        for directory in ("bin", "etc", "tmp", "work", "proc", "sys", "dev", "home/skm"):
            add_dir(directory, 0o1777 if directory == "tmp" else 0o755)
        for name in ("sh", "ls", "cat", "true", "false"):
            found = shutil.which(name)
            if not found:
                continue
            real = Path(found).resolve()
            add_file(f"bin/{name}", real, 0o755)
            add_file(f"usr/bin/{name}", real, 0o755)
            out = subprocess.run((ldd, str(real)), capture_output=True, text=True, check=False).stdout
            for token in out.split():
                if token.startswith("/"):
                    add_file(token, Path(token).resolve(), 0o755)
        init_src = shutil.which("sh") or "/bin/sh"
        add_file("bin/skm-init", Path(init_src).resolve(), 0o755)
    return buf.getvalue()


@pytest.fixture
def live_container_image(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[str]:
    """Restore captured host Docker config or lazily build a local runnable archive so nothing skips."""
    host_env = captured_host_env(request.config)
    real_home = host_env.get("HOME", "")
    if real_home and not os.environ.get("DOCKER_CONFIG"):
        monkeypatch.setenv("DOCKER_CONFIG", str(Path(real_home) / ".docker"))
    explicit = os.environ.get("SKM_TEST_CONTAINER_IMAGE") or host_env.get("SKM_TEST_CONTAINER_IMAGE", "")
    image = explicit.strip()
    if shutil.which("docker") is None:
        pytest.fail("the docker CLI is missing", pytrace=False)
    if image:
        yield image
        return
    suffix = uuid4().hex
    tag = f"skm-live-canary-{suffix}:own"
    pinned = "skm-live-canary@sha256:" + hashlib.sha256(tag.encode()).hexdigest()
    raw_cli = docker_cli
    loaded = False

    def ensure_loaded() -> None:
        nonlocal loaded
        if loaded:
            return
        arch = raw_cli(("docker", "version", "--format", "{{.Server.Arch}}"))
        if arch.exit_code != 0 or not arch.stdout.strip():
            return
        archive = tmp_path / f"skm-live-canary-{suffix}.tar"
        default_path = "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        own_image_archive(
            archive,
            tag,
            arch.stdout.strip(),
            {"Env": [default_path], "Entrypoint": ["/bin/skm-init", "-c", 'exec "$@"', "--"]},
            layer=runnable_layer_tar(),
        )
        res = raw_cli(("docker", "load", "--input", str(archive)))
        assert res.exit_code == 0, res.stderr
        loaded = True

    translated = through_tag(raw_cli, pinned, tag)

    def runner(argv: Sequence[str]) -> DockerResult:
        ensure_loaded()
        return translated(argv) if loaded else raw_cli(argv)

    monkeypatch.setattr(sys.modules[__name__], "docker_cli", runner)
    try:
        yield pinned
    finally:
        if loaded:
            raw_cli(("docker", "image", "rm", "--force", tag))


def docker_client_env() -> dict[str, str]:
    """Only what the client needs to find its daemon; the rest of the host environment stays out."""
    env = {name: os.environ[name] for name in DOCKER_CLIENT_ENV if name in os.environ}
    if (
        "DOCKER_HOST" not in env
        and "DOCKER_CONTEXT" not in env
        and not (Path(env.get("DOCKER_CONFIG", "")) / "contexts").is_dir()
        and not Path("/var/run/docker.sock").exists()
        and hasattr(os, "getuid")
    ):
        rootless = Path(f"/run/user/{os.getuid()}/docker.sock")
        try:
            if rootless.is_socket():
                env["DOCKER_HOST"] = f"unix://{rootless}"
        except OSError:
            pass
    return env


def docker_cli(argv: Sequence[str]) -> DockerResult:
    done = subprocess.run(
        argv, capture_output=True, text=True, timeout=120, check=False, env=docker_client_env()
    )
    return DockerResult(done.returncode, done.stdout, done.stderr)


def mapped_host_uid(uid_map: str, uid: int) -> int:
    """The host UID of ``uid`` by the kernel's ``/proc/<pid>/uid_map`` of the container."""
    for line in uid_map.splitlines():
        inside, outside, count = (int(field) for field in line.split())
        if inside <= uid < inside + count:
            return outside + uid - inside
    raise AssertionError(f"uid {uid} is not mapped by {uid_map!r}")


def test_mapped_host_uid_reads_identity_and_rootless_maps() -> None:
    assert mapped_host_uid("         0          0 4294967295\n", 1000) == 1000
    rootless = "         0       1000          1\n         1     100000      65536\n"
    assert mapped_host_uid(rootless, 0) == 1000
    assert mapped_host_uid(rootless, 1000) == 100999
    with pytest.raises(AssertionError, match="not mapped"):
        mapped_host_uid("0 1000 1\n", 1000)


def mount_options(mountinfo: str, target: str) -> frozenset[str]:
    """The kernel's flags of the topmost mount at ``target`` in ``/proc/<pid>/mountinfo``. Field 6 belongs to
    the mount; the options after `` - `` belong to the filesystem and stay ``rw`` under a read-only bind."""
    options: frozenset[str] | None = None
    for line in mountinfo.splitlines():
        fields = line.split()
        if fields[4] == target:
            options = frozenset(fields[5].split(","))
    if options is None:
        raise AssertionError(f"nothing is mounted at {target}: {mountinfo!r}")
    return options


def test_mount_options_reads_the_flags_of_the_mount_not_of_its_filesystem() -> None:
    mountinfo = (
        "10 1 0:40 / / ro,relatime master:1 - overlay overlay rw,lowerdir=/l\n"
        "11 10 8:1 /home/w/work /work ro,relatime - ext4 /dev/sda1 rw\n"
        "12 10 8:1 /home/w/rw /rw rw,relatime - ext4 /dev/sda1 ro\n"
        "13 10 8:1 /below /stacked ro - ext4 /dev/sda1 rw\n"
        "14 10 8:1 /above /stacked rw - ext4 /dev/sda1 rw\n"
    )
    assert "ro" in mount_options(mountinfo, "/")
    assert "ro" in mount_options(mountinfo, "/work")
    assert "ro" not in mount_options(mountinfo, "/rw"), "a read-only filesystem is no read-only mount"
    assert "ro" not in mount_options(mountinfo, "/stacked"), "the last mount is the one a path reaches"
    with pytest.raises(AssertionError, match="nothing is mounted"):
        mount_options(mountinfo, "/work/.git")


def without_readonly(runner: Callable[[Sequence[str]], DockerResult]) -> Callable[..., DockerResult]:
    """The mutation of the live control: ``create`` binds lose ``readonly``, nothing else changes."""

    def mutated(argv: Sequence[str]) -> DockerResult:
        if argv[1] != "create":
            return runner(argv)
        return runner(
            [item.removesuffix(",readonly") if item.startswith("type=bind,") else item for item in argv]
        )

    return mutated


def create_with(
    runner: Callable[[Sequence[str]], DockerResult], *flags: str, network: str | None = None
) -> Callable[..., DockerResult]:
    """A create by anyone who can reach the daemon and copy the labels: the same argv plus ``flags``. They go
    right after ``create``, since the first word that is neither a flag nor its value is the image."""

    def mutated(argv: Sequence[str]) -> DockerResult:
        if argv[1] != "create":
            return runner(argv)
        call = list(argv)
        if network is not None:
            call[call.index("--network") + 1] = network
        return runner([*call[:2], *flags, *call[2:]])

    return mutated


def test_the_foreign_create_keeps_the_owner_labels_and_changes_only_what_it_was_told_to(
    tmp_path: Path,
) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    argv = backend.create_argv(["agent"], Spec(work_dir(tmp_path)), env_file=None)  # type: ignore[attr-defined]
    recorded: list[tuple[str, ...]] = []

    def recording(call: Sequence[str]) -> DockerResult:
        recorded.append(tuple(call))
        return DockerResult(0, "")

    create_with(recording, "--privileged", network="bridge")(argv)
    (call,) = recorded
    assert call[:3] == ("docker", "create", "--privileged")
    assert call[call.index("--network") + 1] == "bridge"
    assert [item for item in call if item.startswith("skm.")] == [
        item for item in argv if item.startswith("skm.")
    ]
    assert call[-2:] == argv[-2:]
    create_with(recording)(("docker", "inspect", "x"))
    assert recorded[-1] == ("docker", "inspect", "x")


def test_the_mutation_strips_readonly_from_the_binds_of_create_only(tmp_path: Path) -> None:
    docker = FakeDocker()
    backend = container_backend(tmp_path, docker)
    work = work_dir(tmp_path)
    argv = backend.create_argv(["agent"], Spec(work, writable=(), readable=(work,)), env_file=None)  # type: ignore[attr-defined]
    without_readonly(docker)(argv)
    readonly = f"dst={WORKDIR},readonly"
    assert docker.calls[-1] == tuple(item.replace(readonly, f"dst={WORKDIR}") for item in argv)
    without_readonly(docker)(("docker", "inspect", "type=bind,readonly"))
    assert docker.calls[-1][-1] == "type=bind,readonly"


def test_live_container_hides_host_secrets_blocks_outside_writes_and_has_no_network(  # noqa: PLR0915
    tmp_path: Path, live_container_image: str
) -> None:
    """Runs whichever way this daemon maps UIDs and never skips for it. An identity daemon must serve a writer
    that is the worker on the host and still stop it at a protected hole. A remapping daemon must refuse that
    unit before create and before start, and the read-only unit must run; the kernel's own map says which of
    the two is due. A refused write proves nothing there, because the foreign UID is refused anyway, so the
    kernel's mount flags are read and the same unit without ``readonly`` must write to the test's own 0777
    directory; no other mode changes."""
    secret = tmp_path / "host-secret"
    secret.write_text("canary")
    work = work_dir(tmp_path)
    marker = work / "marker"
    marker.write_text("visible")
    marker.chmod(0o644)
    (work / ".git").mkdir()
    uid = os.getuid() or 1000
    persisted: list[CreatedContainer] = []
    litter: list[CreatedContainer] = []  # left by this test and refused on purpose, so never in the markers
    settings = ContainerSettings(image=live_container_image, uid=uid, gid=os.getgid() or 1000)

    def backend(runner: Callable[[Sequence[str]], DockerResult]) -> Any:
        return container_isolation(
            settings, runner=runner, persist=persisted.append, client_env=docker_client_env()
        )

    isolation = backend(docker_cli)

    def run(using: Any, spec: Spec, work_check: str) -> tuple[str, str]:
        script = (
            f'[ ! -e "{secret}" ] || exit 11; (: > /etc/skm-canary) 2>/dev/null && exit 12; '
            '[ "$(ls /sys/class/net)" = "lo" ] || exit 13; : > /tmp/skm-canary || exit 15; '
            f'[ "$(cat /work/marker)" = visible ] || exit 16; {work_check} '
            "cat /proc/self/uid_map && echo --- && cat /proc/self/mountinfo"
        )
        wrapped = using.wrap(["sh", "-c", script], spec)
        done = subprocess.run(
            wrapped.argv, capture_output=True, text=True, timeout=120, check=False, env=wrapped.env
        )
        assert done.returncode == 0, (done.returncode, done.stderr)
        uid_map, _, mountinfo = done.stdout.partition("---\n")
        assert "ro" in mount_options(mountinfo, "/"), "the root is not mounted read-only"
        return uid_map, mountinfo

    writer = Spec(work, protected=(work / ".git",), owner=make_owner(uuid4().hex))
    writing = ": > /work/inside || exit 14; (: > /work/.git/hole) 2>/dev/null && exit 17; "
    refused: CapabilityUnavailable | None = None
    try:
        try:
            uid_map, mountinfo = run(isolation, writer, writing)
        except CapabilityUnavailable as error:
            refused = error
        if refused is None:
            assert mapped_host_uid(uid_map, uid) == uid, "the daemon denied a remapping the kernel reports"
            assert (work / "inside").stat().st_uid == uid
            assert not (work / ".git" / "hole").exists()
            assert "rw" in mount_options(mountinfo, "/work")
            assert "ro" in mount_options(mountinfo, "/work/.git")
        else:
            assert refused.details["reason"] == "daemon_uid_not_identity", refused.details
            assert persisted == [], "refused before create"

            # what a dead client left behind: a real writable container of this owner, never started
            assert docker_cli(isolation.create_argv(["true"], writer, env_file=None)).exit_code == 0
            left = isolation.recover(writer.owner)
            assert left is not None
            with pytest.raises(CapabilityUnavailable) as recovered:
                isolation.wrap(["true"], writer)
            persisted.append(left)
            assert recovered.value.details["reason"] == "daemon_uid_not_identity", recovered.value.details
            state = docker_cli(("docker", "inspect", "--format", "{{.State.Status}}", left.container_id))
            assert state.stdout.strip() == "created"
            # this daemon's own report of the mounts decides where the request no longer says so
            with pytest.raises(CapabilityUnavailable) as recovered:
                isolation.wrap(["true"], Spec(work, writable=(), readable=(work,), owner=writer.owner))
            assert recovered.value.details["reason"] == "daemon_uid_not_identity", recovered.value.details
            kept = Spec(work, writable=(), readable=(work,), owner=make_owner(uuid4().hex))
            assert docker_cli(isolation.create_argv(["true"], kept, env_file=None)).exit_code == 0
            wrapped = isolation.wrap(["true"], kept)
            started = subprocess.run(
                wrapped.argv, capture_output=True, text=True, timeout=120, check=False, env=wrapped.env
            )
            assert started.returncode == 0, (started.returncode, started.stderr)

            # the foreign UID may write here, so only the mount can be what stops the read-only unit
            open_work = tmp_path / "open-work"
            open_work.mkdir()
            open_work.chmod(0o777)
            marker = open_work / "marker"
            marker.write_text("visible")
            marker.chmod(0o644)

            def reader() -> Spec:
                return Spec(open_work, writable=(), readable=(open_work,), owner=make_owner(uuid4().hex))

            uid_map, mountinfo = run(isolation, reader(), "(: > /work/inside) 2>/dev/null && exit 14; ")
            assert mapped_host_uid(uid_map, uid) != uid, "the daemon claimed a remapping the kernel denies"
            assert "ro" in mount_options(mountinfo, "/work"), "the kernel does not hold /work read-only"
            assert not (open_work / "inside").exists()

            mutated = backend(without_readonly(docker_cli))
            _, mountinfo = run(mutated, reader(), ": > /work/inside || exit 14; ")
            assert "ro" not in mount_options(mountinfo, "/work"), "the flags do not tell the mutation apart"
            assert (open_work / "inside").exists(), "the control proves nothing: the write was not possible"

        # -- what a recovered container may be, whichever way this daemon maps UIDs ----------------------
        marker = tmp_path / "ran"
        marker.mkdir()
        marker.chmod(0o777)

        def unit(*argv: str, **fields: Any) -> tuple[list[str], Spec]:
            """A read-only unit that serves on any daemon, as ``argv`` and ``spec`` of ``wrap``."""
            owner = fields.pop("owner", None) or make_owner(uuid4().hex)
            fields.setdefault("readable", (marker,))
            return list(argv), Spec(marker, writable=(), owner=owner, **fields)

        def left_behind(creator: Any, argv: list[str], spec: Spec, *env_file: Path) -> str:
            done = creator(isolation.create_argv(argv, spec, env_file=env_file[0] if env_file else None))
            assert done.exit_code == 0, done.stderr
            found = isolation.recover(spec.owner)
            assert found is not None
            litter.append(found)
            return found.container_id

        def status(container_id: str) -> str:
            return docker_cli(
                ("docker", "inspect", "--format", "{{.State.Status}}", container_id)
            ).stdout.strip()

        def no_probes_left() -> bool:
            listed = docker_cli(
                ("docker", "ps", "-a", "--filter", "label=skm.confinement_baseline", "--format", "{{.ID}}")
            )
            return listed.exit_code == 0 and not listed.stdout.strip()

        def recovery_refused(argv: list[str], spec: Spec) -> dict[str, JsonValue]:
            before = len(persisted)
            with pytest.raises(CapabilityUnavailable) as caught:
                isolation.wrap(argv, spec)
            assert len(persisted) == before, "a refused container got no marker"
            return dict(caught.value.details)

        def mismatch(details: Mapping[str, JsonValue], *fields: str) -> None:
            assert details["reason"] == "recovered_config_mismatch", details
            assert set(fields) <= set(details["differs"]), details  # type: ignore[arg-type]

        # a neighbour with another owner must come out of all this as it went in
        neighbour = left_behind(docker_cli, *unit("true"))

        # the positive control: this daemon's own report of a create of this request is what we expect
        same_argv, same = unit("sh", "-c", "echo recovered-and-started")
        same_id = left_behind(docker_cli, same_argv, same)
        wrapped = isolation.wrap(same_argv, same)
        assert wrapped.argv[-1] == same_id
        assert status(same_id) == "created", "wrap never starts anything by itself"
        assert no_probes_left()
        started = subprocess.run(
            wrapped.argv, capture_output=True, text=True, timeout=120, check=False, env=wrapped.env
        )
        assert started.returncode == 0, (started.returncode, started.stderr)
        assert "recovered-and-started" in started.stdout
        assert status(same_id) == "exited"
        details = recovery_refused(same_argv, same)
        assert details["reason"] == "owner_container_not_fresh", details
        if refused is None:  # the writable bind of a real create, on the daemon that can serve one
            left_writer = Spec(work, protected=(work / ".git",), owner=make_owner(uuid4().hex))
            writer_id = left_behind(docker_cli, ["true"], left_writer)
            assert isolation.wrap(["true"], left_writer).argv[-1] == writer_id

        # the same request with a secret: the env file is parsed as modelled, and values stay out of reports
        token = "live-" + uuid4().hex
        env_file = tmp_path / "env-file"
        env_file.write_text(f"API_TOKEN={token}\n")
        env_file.chmod(0o600)
        secret_argv, secret_unit = unit("true", env={"API_TOKEN": token, "LANG": "C"})
        secret_id = left_behind(docker_cli, secret_argv, secret_unit, env_file)
        assert isolation.wrap(secret_argv, secret_unit).argv[-1] == secret_id
        other_secret = Spec(
            marker,
            writable=(),
            readable=(marker,),
            owner=secret_unit.owner,
            env={"API_TOKEN": "other-" + token, "LANG": "C"},
        )
        details = recovery_refused(secret_argv, other_secret)
        mismatch(details, "Config.Env")
        assert token not in json.dumps(details), "the value of a secret reached a report"
        assert status(secret_id) == "created"

        # one container, requests that differ from what it holds: command, environment, mount, network
        kept_argv, kept_unit = unit("true")
        kept_id = left_behind(docker_cli, kept_argv, kept_unit)
        other_mount = tmp_path / "other-mount"
        other_mount.mkdir()
        for argv, spec, *fields in (
            (["false"], kept_unit, "Config.Cmd", "Args"),
            (
                kept_argv,
                Spec(marker, writable=(), readable=(marker,), owner=kept_unit.owner, env={"EXTRA": "1"}),
                "Config.Env",
            ),
            (
                kept_argv,
                Spec(other_mount, writable=(), readable=(other_mount,), owner=kept_unit.owner),
                "Mounts",
                "HostConfig.Mounts",
            ),
            (
                kept_argv,
                Spec(marker, writable=(), readable=(), owner=kept_unit.owner),
                "Mounts",
                "HostConfig.Mounts",
            ),
        ):
            mismatch(recovery_refused(argv, spec), *fields)
        wider = container_isolation(
            replace(settings, memory="2g", pids_limit=64),
            runner=docker_cli,
            persist=persisted.append,
            client_env=docker_client_env(),
        )
        before = len(persisted)
        with pytest.raises(CapabilityUnavailable) as caught:
            wider.wrap(kept_argv, kept_unit)  # type: ignore[attr-defined]
        assert len(persisted) == before
        mismatch(caught.value.details, "HostConfig.Memory", "HostConfig.PidsLimit")
        assert status(kept_id) == "created"

        # containers carrying the owner's labels, created by anyone: the labels do not make them ours
        for flags, network, fields in FORGED_CREATES:
            named = [flag.format(other=other_mount) for flag in flags]
            forged_argv, forged_unit = unit("true")
            forged = left_behind(create_with(docker_cli, *named, network=network), forged_argv, forged_unit)
            mismatch(recovery_refused(forged_argv, forged_unit), *fields)
            assert status(forged) == "created", "a refused container was started or removed"

        # an unprovable answer about a real container: the daemon's real report, one key short
        def without_key(key: str) -> Callable[[Sequence[str]], DockerResult]:
            def answering(argv: Sequence[str]) -> DockerResult:
                done = docker_cli(argv)
                if argv[1:3] != ("inspect", "--type"):
                    return done
                [record] = json.loads(done.stdout)
                del record["HostConfig"][key]
                return DockerResult(done.exit_code, json.dumps([record]), done.stderr)

            return answering

        omitting = container_isolation(
            settings,
            runner=without_key("Privileged"),
            persist=persisted.append,
            client_env=docker_client_env(),
        )
        omitted_argv, omitted_unit = unit("true")
        omitted = left_behind(docker_cli, omitted_argv, omitted_unit)
        with pytest.raises(CapabilityUnavailable) as caught:
            omitting.wrap(omitted_argv, omitted_unit)  # type: ignore[attr-defined]
        assert caught.value.details["reason"] == "recovered_config_unproven", caught.value.details
        assert caught.value.details["unproven"] == ["HostConfig.Privileged"]
        assert status(omitted) == "created"

        # protected paths one short of what this daemon really gave: present, and still not this daemon's
        def shrunk(container_id: str, key: str) -> Callable[[Sequence[str]], DockerResult]:
            def answering(argv: Sequence[str]) -> DockerResult:
                done = docker_cli(argv)
                if argv[1:3] != ("inspect", "--type") or argv[-1] != container_id:
                    return done
                [record] = json.loads(done.stdout)
                assert len(record["HostConfig"][key]) > 1, record["HostConfig"][key]
                record["HostConfig"][key] = record["HostConfig"][key][1:]
                return DockerResult(done.exit_code, json.dumps([record]), done.stderr)

            return answering

        for key in ("MaskedPaths", "ReadonlyPaths"):
            shrunk_argv, shrunk_unit = unit("true")
            shrunk_id = left_behind(docker_cli, shrunk_argv, shrunk_unit)
            shrinking = container_isolation(
                settings,
                runner=shrunk(shrunk_id, key),
                persist=persisted.append,
                client_env=docker_client_env(),
            )
            before = len(persisted)
            with pytest.raises(CapabilityUnavailable) as caught:
                shrinking.wrap(shrunk_argv, shrunk_unit)  # type: ignore[attr-defined]
            assert len(persisted) == before
            mismatch(caught.value.details, f"HostConfig.{key}")
            assert status(shrunk_id) == "created"
        assert no_probes_left()

        assert status(neighbour) == "created", "another owner's container was touched"
    finally:
        for created in (*persisted, *litter):
            isolation.stop(created)


def own_image_archive(
    archive: Path,
    tag: str,
    architecture: str,
    config: Mapping[str, JsonValue],
    layer: bytes = bytes(1024),
) -> None:
    """A ``docker load`` archive of an image that needs no registry and no base: one layer and ``config``."""
    diff_id = hashlib.sha256(layer).hexdigest()
    document = json.dumps(
        {
            "architecture": architecture,
            "os": "linux",
            "created": "2026-01-01T00:00:00Z",
            "config": config,
            "rootfs": {"type": "layers", "diff_ids": [f"sha256:{diff_id}"]},
        }
    ).encode()
    config_name = f"{hashlib.sha256(document).hexdigest()}.json"
    layer_name = f"{diff_id}/layer.tar"
    manifest = json.dumps([{"Config": config_name, "RepoTags": [tag], "Layers": [layer_name]}]).encode()
    with tarfile.open(archive, "w") as stream:
        for name, data in ((config_name, document), (layer_name, layer), ("manifest.json", manifest)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            stream.addfile(info, io.BytesIO(data))


def through_tag(
    runner: Callable[[Sequence[str]], DockerResult], pinned: str, tag: str
) -> Callable[[Sequence[str]], DockerResult]:
    """A digest needs a registry, a loaded image has only its tag. So the backend asks for ``pinned`` and the
    daemon is told ``tag``, its report says ``pinned`` again; nothing else of a call or an answer changes."""

    def translated(argv: Sequence[str]) -> DockerResult:
        done = runner([tag if item == pinned else item for item in argv])
        if argv[1:3] != ("inspect", "--type") or done.exit_code != 0:
            return done
        [record] = json.loads(done.stdout)
        if record["Config"]["Image"] == tag:
            record["Config"]["Image"] = pinned
        return DockerResult(0, json.dumps([record]), done.stderr)

    return translated


def live_volume_names(container: str) -> list[str]:
    done = docker_cli(("docker", "inspect", "--type", "container", container))
    assert done.exit_code == 0, done.stderr
    return [mount["Name"] for mount in json.loads(done.stdout)[0]["Mounts"] if mount["Type"] == "volume"]


def live_volume_there(name: str) -> bool:
    return docker_cli(("docker", "volume", "inspect", name)).exit_code == 0


def test_live_probe_takes_its_own_anonymous_volumes_and_nothing_else(  # noqa: PLR0915
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On the real daemon, with an image, volumes and containers this test made and removes by exact name: the
    probe's volumes go, a named one and those of other containers stay, a probe that keeps a volume refuses.
    The image also carries what the daemon normalizes: an entrypoint of one empty string, repeated vars."""
    real_home = captured_host_env(request.config).get("HOME", "")
    if real_home and not os.environ.get("DOCKER_CONFIG"):
        monkeypatch.setenv("DOCKER_CONFIG", str(Path(real_home) / ".docker"))
    architecture = docker_cli(("docker", "version", "--format", "{{.Server.Arch}}")).stdout.strip()
    assert architecture
    suffix = uuid4().hex
    tag = f"skm-live-probe-{suffix}:own"
    pinned = "skm-live-probe@sha256:" + hashlib.sha256(tag.encode()).hexdigest()
    named = f"skm-live-named-{suffix}"
    data_path = "/skm-live-data"
    containers: list[str] = []
    volumes: list[str] = [named]
    image_loaded = False
    translated = through_tag(docker_cli, pinned, tag)
    settings = ContainerSettings(image=pinned, uid=os.getuid() or 1000, gid=os.getgid() or 1000)
    persisted: list[CreatedContainer] = []
    probes: list[tuple[str, list[str]]] = []

    def watching(argv: Sequence[str]) -> DockerResult:
        """Learns from the daemon's own report what each probe holds; cleans up after every test path."""
        done = translated(argv)
        if argv[1:3] == ("inspect", "--type") and done.exit_code == 0:
            record = json.loads(done.stdout)[0]
            if str(record.get("Name", "")).startswith("/skm-baseline-"):
                names = [m["Name"] for m in record["Mounts"] if m["Type"] == "volume"]
                probes.append((argv[-1], names))
                containers.append(argv[-1])
                volumes.extend(names)
        return done

    def backend(runner: Callable[[Sequence[str]], DockerResult]) -> Any:
        return container_isolation(
            settings, runner=runner, persist=persisted.append, client_env=docker_client_env()
        )

    def left_behind(argv: list[str], spec: Spec) -> str:
        env_file = tmp_path / "request.env"
        env_file.touch(mode=0o600, exist_ok=False)
        try:
            env_file.write_text(f"SKM_ASKED={spec.env['SKM_ASKED']}\n", encoding="utf-8")
            done = translated(backend(translated).create_argv(argv, spec, env_file=env_file))
        finally:
            env_file.unlink()
        assert done.exit_code == 0, done.stderr
        container = done.stdout.strip()
        containers.append(container)
        volumes.extend(live_volume_names(container))
        return container

    def foreign(*flags: str) -> str:
        done = docker_cli(("docker", "create", "--pull", "never", *flags, tag, "/skm-is-never-started"))
        assert done.exit_code == 0, done.stderr
        containers.append(done.stdout.strip())
        return containers[-1]

    def unit(**fields: Any) -> tuple[list[str], Spec]:
        return ["/skm-is-never-started"], Spec(
            work_dir(tmp_path), writable=(), readable=(), owner=make_owner(uuid4().hex), **fields
        )

    try:
        archive = tmp_path / "own-image.tar"
        own_image_archive(
            archive,
            tag,
            architecture,
            {
                "Entrypoint": [""],
                "Env": ["SKM_TWICE=first", "SKM_TWICE=second", "SKM_ASKED=image", "SKM_ASKED=image-again"],
                "Volumes": {data_path: {}, "/tmp": {}},  # noqa: S108
            },
        )
        loaded = docker_cli(("docker", "load", "--input", str(archive)))
        assert loaded.exit_code == 0, loaded.stderr
        image_loaded = True
        created_volume = docker_cli(("docker", "volume", "create", named))
        assert created_volume.exit_code == 0, created_volume.stderr

        # those who must come out as they went in: a user's named volume, another container's anonymous one
        user_container = foreign("--mount", f"type=volume,src={named},dst={data_path}")
        other_container = foreign()
        [*others] = live_volume_names(other_container)
        assert others, "an image volume gives a container an anonymous volume"
        volumes.extend(others)

        # the daemon's own merge of this image, and an admission of exactly that
        argv, spec = unit(env={"SKM_ASKED": "request"})
        mine = left_behind(argv, spec)
        report = docker_cli(("docker", "inspect", "--type", "container", mine))
        record = json.loads(report.stdout)[0]
        assert record["Config"]["Entrypoint"] in (None, [])
        assert (record["Path"], record["Args"]) == (argv[0], [])
        env = record["Config"]["Env"]
        assert "SKM_TWICE=first" in env
        assert "SKM_TWICE=second" not in env
        assert [line for line in env if line.startswith("SKM_ASKED=")] == ["SKM_ASKED=request"]
        kept = live_volume_names(mine)
        assert kept

        assert backend(watching).wrap(argv, spec).argv[-1] == mine
        (probe, probe_volumes) = probes.pop()
        assert probe_volumes, "the probe held no volume, so this proved nothing"
        assert not any(live_volume_there(name) for name in probe_volumes), "a volume of the probe stayed"
        assert docker_cli(("docker", "inspect", "--type", "container", probe)).exit_code != 0
        assert live_volume_there(named), "a user's named volume was removed"
        assert all(live_volume_there(name) for name in [*others, *kept]), "a volume of another container"
        for container in (user_container, other_container, mine):
            state = docker_cli(("docker", "inspect", "--format", "{{.State.Status}}", container))
            assert state.stdout.strip() == "created", "another container was touched"

        # the control: without ``--volumes`` the same probe really leaves its volume, and that is what refuses
        def keeping_volumes(call: Sequence[str]) -> DockerResult:
            if call[1] == "rm":
                return watching([item for item in call if item != "--volumes"])
            return watching(call)

        argv, spec = unit(env={"SKM_ASKED": "request"})
        left_behind(argv, spec)
        before = len(persisted)
        with pytest.raises(CapabilityUnavailable) as caught:
            backend(keeping_volumes).wrap(argv, spec)
        assert caught.value.details["reason"] == "recovered_config_unproven", caught.value.details
        (_, probe_volumes) = probes.pop()
        assert set(caught.value.details["volumes"]) == set(probe_volumes)  # type: ignore[arg-type]
        assert probe_volumes
        assert all(live_volume_there(name) for name in probe_volumes), "the control proves nothing"
        assert len(persisted) == before

        # someone mounts the probe's volume before the ``rm``: it is theirs now, so it stays and refuses
        def taking_the_volume(call: Sequence[str]) -> DockerResult:
            before_probes = len(probes)
            done = watching(call)
            if len(probes) > before_probes:
                foreign("--mount", f"type=volume,src={probes[-1][1][0]},dst={data_path}")
            return done

        argv, spec = unit(env={"SKM_ASKED": "request"})
        left_behind(argv, spec)
        with pytest.raises(CapabilityUnavailable) as caught:
            backend(taking_the_volume).wrap(argv, spec)
        assert caught.value.details["reason"] == "recovered_config_unproven", caught.value.details
        (_, probe_volumes) = probes.pop()
        assert probe_volumes[0] in caught.value.details["volumes"]  # type: ignore[operator]
        assert live_volume_there(probe_volumes[0]), "a volume another container uses was removed"
        state = docker_cli(("docker", "inspect", "--format", "{{.State.Status}}", containers[-1]))
        assert state.stdout.strip() == "created"
        assert len(persisted) == before
    finally:
        for container in containers:
            docker_cli(("docker", "rm", "--force", "--volumes", container))
        for name in dict.fromkeys(volumes):
            docker_cli(("docker", "volume", "rm", name))
        if image_loaded:
            docker_cli(("docker", "image", "rm", "--force", tag))


def test_the_own_image_archive_holds_exactly_what_was_asked(tmp_path: Path) -> None:
    archive = tmp_path / "image.tar"
    config: dict[str, JsonValue] = {"Entrypoint": [""], "Env": ["A=1", "A=2"]}
    own_image_archive(archive, "own:tag", "amd64", config)
    with tarfile.open(archive) as stream:
        [manifest] = json.load(stream.extractfile("manifest.json"))  # type: ignore[arg-type]
        document = stream.extractfile(manifest["Config"]).read()  # type: ignore[union-attr]
        layer = stream.extractfile(manifest["Layers"][0]).read()  # type: ignore[union-attr]
    assert manifest["RepoTags"] == ["own:tag"]
    assert manifest["Config"] == f"{hashlib.sha256(document).hexdigest()}.json"
    image = json.loads(document)
    assert image["config"] == config
    assert image["rootfs"]["diff_ids"] == [f"sha256:{hashlib.sha256(layer).hexdigest()}"]


def test_through_tag_changes_the_image_reference_and_nothing_else() -> None:
    calls: list[list[str]] = []
    report = [{"Config": {"Image": "own:tag", "Env": ["own:tag"]}, "Image": "own:tag"}]

    def runner(argv: Sequence[str]) -> DockerResult:
        calls.append(list(argv))
        return DockerResult(0, json.dumps(report))

    translated = through_tag(runner, IMAGE, "own:tag")
    assert json.loads(translated(("docker", "inspect", "--type", "container", "x")).stdout) == [
        {"Config": {"Image": IMAGE, "Env": ["own:tag"]}, "Image": "own:tag"}
    ]
    translated(("docker", "create", "--name", "n", IMAGE, "cmd"))
    assert calls[-1] == ["docker", "create", "--name", "n", "own:tag", "cmd"]
    assert json.loads(translated(("docker", "image", "inspect", IMAGE)).stdout) == report
    assert calls[-1] == ["docker", "image", "inspect", "own:tag"]


def test_the_canary_image_stays_out_of_tests_that_do_not_ask_for_it() -> None:
    assert "SKM_TEST_CONTAINER_IMAGE" not in os.environ


def nested_canary_run(tmp_path: Path, **env: str) -> tuple[str, Path]:
    """The real runner and ``tests/conftest.py`` over a docker CLI that records its environment and fails."""
    tool = tmp_path / "bin" / "docker"
    tool.parent.mkdir()
    seen = tmp_path / "docker-env"
    tool.write_text(f'#!/bin/sh\nenv > "{seen}"\nexit 1\n')
    tool.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    module = "tests/security/test_sandbox_profiles.py"
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--basetemp={tmp_path / 'base'}",
            f"{module}::{CANARY}",
            f"{module}::test_the_canary_image_stays_out_of_tests_that_do_not_ask_for_it",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=REPOSITORY,
        env={
            "PATH": f"{tool.parent}:{os.environ['PATH']}",
            "HOME": str(home),
            "TMPDIR": os.environ.get("TMPDIR", str(tmp_path)),
            **env,
        },
    )
    return done.stdout + done.stderr, seen


def test_an_explicit_image_reaches_the_canary_under_the_real_conftest(tmp_path: Path) -> None:
    """``pytest_configure`` removes every ``SKM_*``: read at import, the image was gone and it skipped."""
    pinned = "registry.example/canary@sha256:" + "c" * 64
    output, seen = nested_canary_run(
        tmp_path,
        SKM_TEST_CONTAINER_IMAGE=pinned,
        SKM_DATABASE_URL="postgresql://host-secret",
        API_TOKEN="host-secret",
    )
    # the fake daemon refuses: what counts is that nothing skipped
    assert "1 failed, 1 passed" in output, output
    assert "daemon_unavailable" in output, output
    client = dict(line.split("=", 1) for line in seen.read_text().splitlines() if "=" in line)
    assert client["DOCKER_CONFIG"] == str(tmp_path / "home" / ".docker")
    assert "host-secret" not in seen.read_text()
    assert not {"SKM_TEST_CONTAINER_IMAGE", "SKM_DATABASE_URL", "API_TOKEN"} & client.keys()


def test_without_an_explicit_image_the_canary_loads_its_own_archive(tmp_path: Path) -> None:
    output, seen = nested_canary_run(tmp_path)
    assert "1 failed, 1 passed" in output, output
    assert "skipped" not in output, output
    assert "daemon_unavailable" in output, output
    assert seen.exists()
