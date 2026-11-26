"""``container`` profile: ``docker create`` → persist ID → ``docker start --attach <ID>`` (adapters §7.2).

The container owns the process tree. ``wrap`` creates the container with owner labels, persists the immutable
ID and daemon identity before start, and returns a client argv that starts that ID. A create interrupted
before persistence is recovered by verified labels, exact ``docker inspect`` configuration and a live
unstarted baseline probe container (whose anonymous volumes are removed via ``docker rm --volumes`` and
verified absent before admission).
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final, Protocol, cast, override
from uuid import uuid4

from skm.adapters.sandbox.backend import BackendIsolation, Companion, SpecView, WrappedProcess, unavailable
from skm.adapters.sandbox.container_inspect import (
    ABSENT,
    BASELINE_FIELDS,
    CONTAINER_ID,
    PROBE_COMMAND,
    PROBE_LABEL,
    as_flag,
    as_mapping,
    as_number,
    as_strings,
    as_text,
    dig,
    effective_mounts,
    has_writable_mount,
    image_entrypoint,
    inspected_one,
    merged_env,
    probe_volumes,
    requested_mounts,
    returned_id,
    verified_probe_id,
)
from skm.kernel.json_types import JsonValue
from skm.modules.execution.ports import Isolation
from skm.modules.policy.domain.render import IsolationProperty
from skm.modules.runtimes.domain.request import ProcessOwner, ProcessOwnership
from skm.platform.config.sources.hookd_runtime import runtime_overlaps
from skm.platform.process.environment import BASE_ALLOW

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = ["ContainerIsolation", "container_isolation"]

CONTAINER_HOME: Final = "/home/skm"
WORKDIR: Final = "/work"
MATERIALS: Final = "/materials"
_IMAGE: Final = re.compile(r"[A-Za-z0-9./:_-]{1,200}@sha256:[0-9a-f]{64}")
_SIZE: Final = re.compile(r"[0-9]{1,6}[kmg]")
_NETWORK: Final = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_ENV_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LOCALE_ENV: Final = frozenset(
    {"LC_ALL", "LC_COLLATE", "LC_CTYPE", "LC_MESSAGES", "LC_MONETARY", "LC_NUMERIC", "LC_TIME"}
)
_DAEMON_DIRS: Final = ("/run", "/var/run", "/var/lib/docker", "/var/lib/containerd", "/var/lib/containers")
_DAEMON_HOME_DIRS: Final = (".docker", ".local/share/docker", ".local/share/containers")
_NO_SUCH_CONTAINER: Final = re.compile(r"no such (?:object|container): (?P<id>[0-9a-f]{12,64})\b", re.I)
_STOP_SECONDS: Final = 10
_UID_REMAPPING: Final = frozenset({"rootless", "userns"})
_SIZE_UNITS: Final = {"k": 1024, "m": 1024**2, "g": 1024**3}
_DAEMON_CHOSEN: Final = frozenset({"ConsoleSize", "ShmSize"})
_PROBE_NAME_PREFIX: Final = "skm-baseline-"


class ContainerIsolation(Isolation, Protocol):
    """Technology binding of ``Isolation``; the concrete backend is built by ``container_isolation``."""


@dataclass(frozen=True, slots=True)
class DockerResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


type DockerRunner = Callable[[Sequence[str]], DockerResult]


@dataclass(frozen=True, slots=True)
class CreatedContainer:
    """What the worker stores in its marker before ``start``: the immutable ID and the issuing daemon."""

    container_id: str
    daemon_identity: str
    name: str
    owner: ProcessOwner


@dataclass(frozen=True, slots=True)
class CleanupResult:
    confirmed: bool
    state: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class _Daemon:
    runtime: str
    logging_driver: str
    swap_limit: bool
    cgroup_version: str


@dataclass(frozen=True, slots=True)
class _Image:
    image_id: str
    entrypoint: tuple[str, ...]
    env: tuple[str, ...]
    labels: Mapping[str, JsonValue]
    volumes: Mapping[str, JsonValue]
    healthcheck: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ContainerSettings:
    """``worker.isolation.container.*`` plus the uid/gid of the worker process."""

    image: str
    uid: int
    gid: int
    tmp_size: str = "1g"
    pids_limit: int = 512
    memory: str = "4g"
    cpus: float = 2
    network: str | None = None
    allow_full_network: bool = False
    docker: str = "docker"

    def __post_init__(self) -> None:
        if _IMAGE.fullmatch(self.image) is None:
            raise ValueError("the container image must be pinned by digest (name@sha256:<64 hex>)")
        if self.uid <= 0 or self.gid <= 0:
            raise ValueError("the container user must not be root")
        if _SIZE.fullmatch(self.tmp_size) is None or _SIZE.fullmatch(self.memory) is None:
            raise ValueError("tmp_size and memory look like 512m, 4g")
        if not 16 <= self.pids_limit <= 65536 or not 0.1 <= self.cpus <= 256:
            raise ValueError("pids_limit 16..65536, cpus 0.1..256")
        if self.network is not None and _NETWORK.fullmatch(self.network) is None:
            raise ValueError("invalid docker network name")


def _inside(path: str, root: str) -> bool:
    return os.path.commonpath((path, root)) == root


def _mount_path(path: Path | str, what: str, profile: str = "container") -> str:
    text = str(path)
    if not os.path.isabs(text) or any(char in text for char in ",\n\r\0="):
        raise unavailable(profile, "unsafe_mount_path", f"{what} is not a plain absolute path", path=text)
    return os.path.realpath(text)


def _holds_socket(source: str) -> str | None:
    try:
        if stat.S_ISSOCK(os.stat(source).st_mode):
            return source
        pending = [source] if os.path.isdir(source) else []
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    try:
                        if stat.S_ISSOCK(os.stat(entry.path).st_mode):
                            return entry.path
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(entry.path)
                    except OSError:
                        continue
    except FileNotFoundError:
        return None
    except OSError:
        return source
    return None


def _needs_env_file(name: str) -> bool:
    """Only base process variables and POSIX locale variables may appear in the public argv."""
    return name not in BASE_ALLOW and name not in _LOCALE_ENV


class _ContainerBackend(BackendIsolation):
    profile: ClassVar[str] = "container"

    def __init__(  # noqa: PLR0913
        self, settings: ContainerSettings, *, runner: DockerRunner,
        persist: Callable[[CreatedContainer], None] | None, companions: Sequence[Companion],
        require: Sequence[IsolationProperty], home: Path | None, client_env: Mapping[str, str],
        env_dir: Path | None, interactive: bool,
    ) -> None:  # fmt: skip
        super().__init__(companions=companions, require=require)
        self._settings = settings
        self._runner = runner
        self._persist = persist
        self._home = home
        self._client_env = dict(client_env)
        self._env_dir = env_dir
        self._interactive = interactive

    def _docker(self, *args: str) -> DockerResult:
        try:
            return self._runner((self._settings.docker, *args))
        except OSError as error:
            return DockerResult(127, "", f"{type(error).__name__}: {error}")

    def _daemon_identity(self) -> str | None:
        result = self._docker("info", "--format", "{{.ID}}")
        text = result.stdout.strip()
        return text if result.exit_code == 0 and text else None

    def _uid_remapping(self) -> frozenset[str] | None:
        result = self._docker("info", "--format", "{{json .SecurityOptions}}")
        try:
            options = json.loads(result.stdout) if result.exit_code == 0 else None
        except ValueError:
            options = None
        if not isinstance(options, list):
            return None
        names: set[str] = set()
        for option in cast("list[JsonValue]", options):
            if not isinstance(option, str):
                return None
            names.update(field.removeprefix("name=") for field in option.split(","))
        return _UID_REMAPPING & names

    def _daemon_facts(self) -> _Daemon | None:
        result = self._docker("info", "--format", "{{json .}}")
        try:
            info: object = json.loads(result.stdout) if result.exit_code == 0 else None
            return _Daemon(
                as_text(dig(info, "DefaultRuntime")),
                as_text(dig(info, "LoggingDriver")),
                as_flag(dig(info, "SwapLimit")),
                as_text(dig(info, "CgroupVersion")),
            )
        except ValueError:
            return None

    def _image_facts(self) -> _Image | None:
        record = inspected_one(self._docker("image", "inspect", self._settings.image))
        if record is None or not isinstance(record.get("Config"), dict):
            return None
        cfg = cast("dict[str, object]", record["Config"])
        try:
            return _Image(
                as_text(record.get("Id")),
                image_entrypoint(cfg.get("Entrypoint")),
                as_strings(cfg.get("Env")),
                as_mapping(cfg.get("Labels")),
                as_mapping(cfg.get("Volumes")),
                as_mapping(cfg.get("Healthcheck")),
            )
        except ValueError:
            return None

    def _require_host_identity(self, *, writable: bool) -> None:
        if not writable:
            return
        remapping = self._uid_remapping()
        if remapping is None:
            raise unavailable(self.profile, "daemon_uid_mapping_unproven", "daemon UID mapping unproven")
        if remapping:
            msg = "container user is not the worker on this daemon"
            raise unavailable(
                self.profile, "daemon_uid_not_identity", msg, remapped_by=list[JsonValue](sorted(remapping))
            )

    def available(self, host: object) -> JsonObject:  # noqa: ARG002
        version = self._docker("version", "--format", "{{.Server.Version}}")
        if version.exit_code != 0 or not version.stdout.strip():
            err = version.stderr.strip()[:200]
            return {"available": False, "reason": f"docker daemon unavailable: {err}"}
        image = self._docker("image", "inspect", self._settings.image)
        if image.exit_code != 0:
            return {"available": False, "reason": f"image {self._settings.image} is not available"}
        return {"available": True, "server_version": version.stdout.strip()}

    @override
    def proven(self, spec: SpecView) -> Mapping[IsolationProperty, str]:
        proven: dict[IsolationProperty, str] = {
            IsolationProperty.FS_WRITE: "container: --read-only root; only rw bind mounts and tmpfs /tmp",
            IsolationProperty.FS_READ: "container: only mounted paths are visible; no home, no docker socket",
            IsolationProperty.CREDENTIALS: "container: only the declared credential files, read-only",
            IsolationProperty.RESOURCES: "container: --memory, --cpus, --pids-limit, tmpfs size",
        }
        if spec.network == "none":
            proven[IsolationProperty.NETWORK_NONE] = "container: --network none"
        if self._persist is not None:
            proven[IsolationProperty.LIFECYCLE] = "container: owned by an ID persisted before start"
        return proven

    def _daemon_endpoints(self, spec: SpecView) -> list[str]:
        found = [os.path.realpath(item) for item in _DAEMON_DIRS]
        if self._home is not None:
            found.extend(os.path.realpath(self._home / item) for item in _DAEMON_HOME_DIRS)
        hosts = (self._client_env.get("DOCKER_HOST"), spec.env.get("DOCKER_HOST"))
        found.extend(
            os.path.realpath(host.removeprefix("unix://"))
            for host in hosts
            if host and host.startswith("unix://")
        )
        return found

    def _forbidden_source(self, source: str, spec: SpecView) -> str | None:
        if runtime_overlaps(Path(source)):
            return "hookd runtime"
        for item in self._daemon_endpoints(spec):
            if _inside(item, source) or _inside(source, item):
                return item
        for item in ("/", *([os.path.realpath(self._home)] if self._home is not None else [])):
            if _inside(item, source):
                return item
        return _holds_socket(source)

    def _mounts(self, spec: SpecView) -> list[tuple[str, str, bool]]:
        workdir = _mount_path(spec.workdir, "workdir")
        materials = None if spec.materials_dir is None else _mount_path(spec.materials_dir, "materials_dir")
        writable = [_mount_path(path, "writable path") for path in spec.writable]
        readable = [_mount_path(path, "readable path") for path in spec.readable]
        protected = [_mount_path(path, "protected path") for path in spec.protected]
        emitted: list[tuple[str, str, bool]] = []

        def destination(path: str) -> str:
            for root, target in ((workdir, WORKDIR), (materials, MATERIALS)):
                if root is not None and _inside(path, root):
                    return target + path[len(root) :]
            return path

        def mount(source: str, target: str, *, writable_mount: bool) -> None:
            guard = self._forbidden_source(source, spec)
            if guard is not None:
                msg = f"{source} would expose {guard}"
                raise unavailable(self.profile, "forbidden_mount", msg, path=source, exposes=guard)
            emitted.append((source, target, writable_mount))

        def granted(path: str, grants: Sequence[str]) -> bool:
            return any(_inside(path, grant) for grant in grants)

        def visible(path: str, *, write: bool) -> bool:
            return any(_inside(path, source) and (rw or not write) for source, _, rw in emitted)

        if granted(workdir, writable):
            mount(workdir, WORKDIR, writable_mount=True)
        elif granted(workdir, readable):
            mount(workdir, WORKDIR, writable_mount=False)
        if materials is not None and granted(materials, [*writable, *readable]):
            mount(materials, MATERIALS, writable_mount=False)
        for path in dict.fromkeys([*writable, *readable]):
            if not visible(path, write=path in writable):
                mount(path, destination(path), writable_mount=path in writable)
        for path in protected:
            if any(_inside(grant, path) for grant in writable):
                raise unavailable(self.profile, "protected_overlap", f"writable inside {path}", path=path)
            for source, target, writable_mount in [*emitted]:
                if not writable_mount or not _inside(path, source):
                    continue
                if path == source or not os.path.lexists(path):
                    raise unavailable(self.profile, "protected_overlap", f"overlap at {path}", path=path)
                mount(path, target + path[len(source) :], writable_mount=False)
        for credential in spec.credential_mounts:
            source, target = credential.get("source"), credential.get("target")
            if not isinstance(source, str) or not isinstance(target, str):
                raise unavailable(self.profile, "credential_mount_invalid", "missing source or target")
            relative = Path(target)
            if relative.is_absolute() or ".." in relative.parts or any(char in target for char in ",\n\r\0="):
                raise unavailable(self.profile, "credential_mount_invalid", "invalid credential target")
            mount(_mount_path(source, "credential"), f"{CONTAINER_HOME}/{target}", writable_mount=False)
        return emitted

    def _network(self, spec: SpecView) -> str:
        if spec.network == "none":
            return "none"
        if spec.network == "full":
            if not self._settings.allow_full_network:
                raise unavailable(self.profile, "network_full_not_enabled", "full network not enabled")
            return "bridge"
        if self._settings.network is None:
            raise unavailable(self.profile, "network_allowlist_unavailable", "no egress network configured")
        return self._settings.network

    def _request_env(self, spec: SpecView) -> dict[str, str]:
        for name, value in spec.env.items():
            if _ENV_NAME.fullmatch(name) is None or any(char in value for char in "\n\r\0"):
                raise unavailable(self.profile, "env_invalid", f"invalid environment variable {name!r}")
        return {**spec.env, "HOME": CONTAINER_HOME}

    def _create_flags(self, name: str, network: str) -> list[str]:
        settings = self._settings
        return [
            "create", "--init", "--pull", "never",
            "--name", name,
            "--user", f"{settings.uid}:{settings.gid}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--read-only", "--tmpfs", f"/tmp:rw,nosuid,nodev,size={settings.tmp_size}",  # noqa: S108
            "--pids-limit", str(settings.pids_limit),
            "--memory", settings.memory, "--cpus", str(settings.cpus),
            "--network", network,
        ]  # fmt: skip

    def create_argv(self, argv: Sequence[str], spec: SpecView, *, env_file: Path | None) -> tuple[str, ...]:
        settings, owner = self._settings, spec.owner
        command = [settings.docker, *self._create_flags(self.container_name(owner), self._network(spec))]
        if self._interactive:
            command.append("--interactive")
        for key, value in self._labels(owner).items():
            command += ["--label", f"{key}={value}"]
        for source, target, writable in self._mounts(spec):
            mount = f"type=bind,src={source},dst={target}" + ("" if writable else ",readonly")
            command += ["--mount", mount]
        command += ["--workdir", WORKDIR, "--env", f"HOME={CONTAINER_HOME}"]
        for name, value in self._request_env(spec).items():
            if name == "HOME":
                continue
            if _needs_env_file(name):
                if env_file is None:
                    raise unavailable(self.profile, "secret_needs_env_file", f"{name} needs an env file")
                continue
            command += ["--env", f"{name}={value}"]
        if env_file is not None:
            command += ["--env-file", str(env_file)]
        return (*command, settings.image, *argv)

    @staticmethod
    def container_name(owner: ProcessOwner) -> str:
        return f"skm-{owner.unit_kind}-{owner.unit_id}"

    @staticmethod
    def _labels(owner: ProcessOwner) -> dict[str, str]:
        return {
            "skm.host": str(owner.host_id), "skm.worker": str(owner.worker_id),
            "skm.attempt": str(owner.attempt_id), "skm.stage_record": str(owner.stage_record_id),
            "skm.unit_kind": owner.unit_kind, "skm.unit_id": str(owner.unit_id),
            "skm.owner_nonce": owner.owner_nonce,
        }  # fmt: skip

    def _secret_env(self, spec: SpecView) -> Path | None:
        secrets = {k: v for k, v in spec.env.items() if _needs_env_file(k) and k != "HOME"}
        if not secrets:
            return None
        handle, name = tempfile.mkstemp(prefix="skm-env-", dir=self._env_dir)
        path = Path(name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write("".join(f"{key}={value}\n" for key, value in secrets.items()))
        except BaseException:
            # a full disk or an interrupt must not leave the secrets written so far behind
            path.unlink(missing_ok=True)
            raise
        return path

    def recover(self, owner: ProcessOwner) -> CreatedContainer | None:
        found = self._find(owner)
        return None if found is None else found[0]

    def _find(self, owner: ProcessOwner) -> tuple[CreatedContainer, dict[str, object]] | None:
        nonce = f"label=skm.owner_nonce={owner.owner_nonce}"
        listed = self._docker("ps", "-a", "--no-trunc", "--filter", nonce, "--format", "{{.ID}}")
        if listed.exit_code != 0:
            err = listed.stderr[:200]
            raise unavailable(self.profile, "daemon_unavailable", "cannot list containers", stderr=err)
        ids = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
        if not ids:
            return None
        if len(ids) > 1:
            raise unavailable(self.profile, "owner_ambiguous", "ambiguous owner", ids=list[JsonValue](ids))
        if CONTAINER_ID.fullmatch(ids[0]) is None:
            raise unavailable(self.profile, "owner_mismatch", "the daemon did not list a container ID")
        identity = self._daemon_identity()
        if identity is None:
            raise unavailable(self.profile, "daemon_unavailable", "daemon identity is unavailable")
        record = inspected_one(self._docker("inspect", "--type", "container", ids[0]))
        labels = None if record is None else dig(record, "Config.Labels")
        name = self.container_name(owner)
        if (
            record is None or record.get("Id") != ids[0] or record.get("Name") != f"/{name}"
            or not isinstance(labels, dict)
            or any(cast("dict[str, JsonValue]", labels).get(k) != v for k, v in self._labels(owner).items())
        ):  # fmt: skip
            raise unavailable(self.profile, "owner_mismatch", "labels of the found container differ")
        return CreatedContainer(ids[0], identity, name, owner), record

    def _admit_recovered(
        self, found: tuple[CreatedContainer, dict[str, object]], argv: Sequence[str], spec: SpecView
    ) -> CreatedContainer:
        created, record = found
        state = dig(record, "State.Status")
        if state != "created":
            msg = f"container is {'unknown' if state is ABSENT else state}"
            cid = created.container_id
            raise unavailable(self.profile, "owner_container_not_fresh", msg, container_id=cid)
        self._require_host_identity(writable=bool(spec.writable) or has_writable_mount(record))
        self._require_same_config(created.container_id, record, argv, spec)
        self._require_daemon_baseline(created, record)
        return created

    def _wanted_config(
        self, owner: ProcessOwner, argv: Sequence[str], spec: SpecView, daemon: _Daemon, image: _Image
    ) -> list[tuple[str, Callable[[object], object], object]]:
        settings = self._settings
        env = self._request_env(spec)
        binds = frozenset(("bind", src, dst, "rw" if rw else "ro") for src, dst, rw in self._mounts(spec))
        network = self._network(spec)
        memory = int(settings.memory[:-1]) * _SIZE_UNITS[settings.memory[-1]]
        program = [*image.entrypoint, *argv]
        cgroups = frozenset({"private", "host"} if daemon.cgroup_version == "1" else {"private"})
        return [
            ("Image", as_text, image.image_id), ("Path", as_text, program[0]),
            ("Args", as_strings, tuple(program[1:])), ("Config.Image", as_text, settings.image),
            ("Config.Cmd", as_strings, tuple(argv)), ("Config.Entrypoint", as_strings, image.entrypoint),
            ("Config.Env", lambda v: frozenset(as_strings(v)), merged_env(env, image.env)),
            ("Config.User", as_text, f"{settings.uid}:{settings.gid}"),
            ("Config.WorkingDir", as_text, WORKDIR),
            ("Config.Labels", as_mapping, {**image.labels, **self._labels(owner)}),
            ("Config.Volumes", as_mapping, dict(image.volumes)),
            ("Config.Healthcheck", lambda v: as_mapping(None if v is ABSENT else v), dict(image.healthcheck)),
            ("Config.OpenStdin", as_flag, self._interactive), ("Config.Tty", as_flag, False),
            ("Mounts", effective_mounts(image.volumes), binds),
            ("NetworkSettings.Networks", lambda v: frozenset(as_mapping(v, None)), frozenset({network})),
            ("HostConfig.Mounts", lambda v: requested_mounts(None if v is ABSENT else v), binds),
            ("HostConfig.NetworkMode", as_text, network), ("HostConfig.Init", as_flag, True),
            ("HostConfig.Privileged", as_flag, False), ("HostConfig.ReadonlyRootfs", as_flag, True),
            ("HostConfig.CapDrop", as_strings, ("ALL",)), ("HostConfig.CapAdd", as_strings, ()),
            ("HostConfig.SecurityOpt", as_strings, ("no-new-privileges",)),
            ("HostConfig.Tmpfs", as_mapping, {"/tmp": f"rw,nosuid,nodev,size={settings.tmp_size}"}),  # noqa: S108
            ("HostConfig.Binds", as_strings, ()), ("HostConfig.VolumesFrom", as_strings, ()),
            ("HostConfig.Memory", as_number, memory),
            ("HostConfig.MemorySwap", as_number, memory * 2 if daemon.swap_limit else -1),
            ("HostConfig.NanoCpus", as_number, int(Fraction(str(settings.cpus)) * 10**9)),
            ("HostConfig.PidsLimit", as_number, settings.pids_limit),
            ("HostConfig.PidMode", as_text, ""), ("HostConfig.UTSMode", as_text, ""),
            ("HostConfig.UsernsMode", as_text, ""),
            ("HostConfig.IpcMode", lambda v: as_text(v) in {"private", "shareable"}, True),
            ("HostConfig.CgroupnsMode", lambda v: as_text(v) in cgroups, True),
            ("HostConfig.Runtime", as_text, daemon.runtime),
            ("HostConfig.LogConfig.Type", as_text, daemon.logging_driver),
            ("HostConfig.RestartPolicy.Name", lambda v: as_text(v) in {"no", ""}, True),
            ("HostConfig.RestartPolicy.MaximumRetryCount", as_number, 0),
            ("HostConfig.AutoRemove", as_flag, False), ("HostConfig.PublishAllPorts", as_flag, False),
            ("HostConfig.PortBindings", as_mapping, {}),
            ("HostConfig.MaskedPaths", lambda v: bool(as_strings(v)), True),
            ("HostConfig.ReadonlyPaths", lambda v: bool(as_strings(v)), True),
        ]  # fmt: skip

    def _require_same_config(
        self, container_id: str, record: Mapping[str, object], argv: Sequence[str], spec: SpecView
    ) -> None:
        daemon, image = self._daemon_facts(), self._image_facts()
        if daemon is None or image is None:
            missing: list[JsonValue] = [n for n, f in (("daemon", daemon), ("image", image)) if f is None]
            self._refuse_differences(container_id, [], missing)
            raise AssertionError
        sections: list[JsonValue] = [
            name
            for name in ("Config", "HostConfig", "NetworkSettings")
            if not isinstance(record.get(name), dict)
        ]
        if sections:
            self._refuse_differences(container_id, [], sections)
        differs: list[JsonValue] = []
        unproven: list[JsonValue] = []
        wanted = self._wanted_config(spec.owner, argv, spec, daemon, image)
        for field, read, value in wanted:
            try:
                if read(dig(record, field)) != value:
                    differs.append(field)
            except ValueError:
                unproven.append(field)
        compared = {field.split(".")[1] for field, _, _ in wanted if field.startswith("HostConfig.")}
        differs.extend(
            f"HostConfig.{key}"
            for key, item in cast("dict[str, object]", record["HostConfig"]).items()
            if key not in compared and key not in _DAEMON_CHOSEN and item
        )
        self._refuse_differences(container_id, differs, unproven)

    def _refuse_differences(
        self, container_id: str, differs: list[JsonValue], unproven: list[JsonValue]
    ) -> None:
        if differs:
            raise unavailable(
                self.profile, "recovered_config_mismatch", "recovered container configuration differs",
                container_id=container_id, differs=differs, unproven=unproven,
            )  # fmt: skip
        if unproven:
            raise unavailable(
                self.profile, "recovered_config_unproven", "recovered container configuration unproven",
                container_id=container_id, unproven=unproven,
            )  # fmt: skip

    def _baseline_probe(self, container_id: str) -> dict[str, object]:
        name = f"{_PROBE_NAME_PREFIX}{uuid4().hex}"
        probe_id: str | None = None
        report: dict[str, object] | None = None
        removed: DockerResult | None = None
        volumes: tuple[str, ...] | None = None
        try:
            answer = self._docker(
                *self._create_flags(name, "none"), "--label", f"{PROBE_LABEL}=true",
                "--workdir", WORKDIR, self._settings.image, PROBE_COMMAND,
            )  # fmt: skip
            probe_id = returned_id(answer)
            report = inspected_one(self._docker("inspect", "--type", "container", probe_id or name))
        finally:
            rm_id = verified_probe_id(report, probe_id, name)
            if rm_id is not None:
                removed = self._docker("rm", "--volumes", rm_id)
        if removed is not None and report is not None:
            try:
                volumes = probe_volumes(report)
            except ValueError:
                volumes = None
        left = [volume for volume in volumes or () if not self._volume_absent(volume)]
        if (
            probe_id is None or report is None or volumes is None or left
            or removed is None or removed.exit_code != 0
        ):  # fmt: skip
            raise unavailable(
                self.profile, "recovered_config_unproven", "baseline probe or its anonymous volumes unproven",
                container_id=container_id, unproven=["baseline"], probe=name, volumes=list[JsonValue](left),
            )  # fmt: skip
        return report

    def _volume_absent(self, name: str) -> bool:
        gone = self._docker("volume", "inspect", name)
        out = gone.stderr.lower()
        return gone.exit_code != 0 and (f"{name}: no such volume" in out or f"no such volume: {name}" in out)

    def _require_daemon_baseline(self, created: CreatedContainer, record: Mapping[str, object]) -> None:
        container_id = created.container_id
        baseline = self._baseline_probe(container_id)
        if self._daemon_identity() != created.daemon_identity:
            self._refuse_differences(container_id, [], ["baseline"])
        differs: list[JsonValue] = []
        unproven: list[JsonValue] = []
        for field, read in BASELINE_FIELDS:
            try:
                value = read(dig(baseline, field))
            except ValueError:
                unproven.append(f"baseline:{field}")
                continue
            try:
                if read(dig(record, field)) != value:
                    differs.append(field)
            except ValueError:
                unproven.append(field)
        self._refuse_differences(container_id, differs, unproven)

    def _state(self, container_id: str) -> str | None:
        result = self._docker("inspect", "--format", "{{.State.Status}}", container_id)
        return result.stdout.strip() if result.exit_code == 0 else None

    def stop(self, created: CreatedContainer) -> CleanupResult:
        identity = self._daemon_identity()
        if identity is None:
            return CleanupResult(False, "unconfirmed", "daemon unreachable: the marker stays")
        if identity != created.daemon_identity:
            return CleanupResult(False, "unconfirmed", "different daemon answers")
        container_id = created.container_id
        self._docker("stop", "--time", str(_STOP_SECONDS), container_id)
        self._docker("kill", container_id)
        state = self._state(container_id)
        if state is None:
            if self._confirmed_absent(created):
                return CleanupResult(True, "removed")
            return CleanupResult(False, "unconfirmed", "state could not be read")
        if state not in {"exited", "created", "dead"}:
            return CleanupResult(False, "unconfirmed", f"container is still {state}")
        self._docker("rm", container_id)
        if self._state(container_id) is None and self._confirmed_absent(created):
            return CleanupResult(True, "removed")
        return CleanupResult(True, "stopped", "stopped; removal not confirmed")

    def _confirmed_absent(self, created: CreatedContainer) -> bool:
        if self._daemon_identity() != created.daemon_identity:
            return False
        gone = self._docker("inspect", created.container_id)
        m = _NO_SUCH_CONTAINER.search(gone.stderr)
        cid = created.container_id
        return gone.exit_code != 0 and m is not None and cid.startswith(m.group("id").lower())

    def wrap(self, argv: list[str] | tuple[str, ...], spec: SpecView) -> WrappedProcess:
        if not argv:
            raise ValueError("argv must not be empty")
        s = self._settings
        ctx = {"image": s.image, "network": s.network or "", "allow_full_network": str(s.allow_full_network)}
        coverage = self.coverage(spec, argv, ctx)
        if IsolationProperty.NETWORK_ALLOWLIST in coverage.required and s.network is None:
            raise unavailable(self.profile, "network_allowlist_unavailable", "no pre-created egress network")
        owner = spec.owner
        found = self._find(owner)
        if found is not None:
            created = self._admit_recovered(found, argv, spec)
        else:
            identity = self._daemon_identity()
            if identity is None:
                raise unavailable(self.profile, "daemon_unavailable", "docker daemon identity is unavailable")
            self._require_host_identity(writable=bool(spec.writable))
            env_file = self._secret_env(spec)
            try:
                result = self._docker(*self.create_argv(argv, spec, env_file=env_file)[1:])
            finally:
                if env_file is not None:
                    env_file.unlink(missing_ok=True)
            created = self._created(result, identity, argv, spec)
        if self._persist is not None:
            try:
                self._persist(created)
            except BaseException:
                self.stop(created)
                raise
        ownership = ProcessOwnership(
            owner=owner, kind="container", ref=created.container_id, daemon_identity=created.daemon_identity
        )
        start = [s.docker, "start", "--attach", *(["--interactive"] if self._interactive else [])]
        return WrappedProcess(
            (*coverage.launch, *start, created.container_id), dict(self._client_env), spec.workdir, ownership
        )

    def _created(
        self, result: DockerResult, identity: str, argv: Sequence[str], spec: SpecView
    ) -> CreatedContainer:
        owner = spec.owner
        container_id = returned_id(result)
        if container_id is not None:
            return CreatedContainer(container_id, identity, self.container_name(owner), owner)
        found = self._find(owner)
        if found is not None:
            return self._admit_recovered(found, argv, spec)
        err = result.stderr.strip()[:300]
        raise unavailable(self.profile, "create_failed", "failed", exit_code=result.exit_code, stderr=err)


def container_isolation(  # noqa: PLR0913
    settings: ContainerSettings, *, runner: DockerRunner,
    persist: Callable[[CreatedContainer], None] | None = None, companions: Sequence[Companion] = (),
    require: Sequence[IsolationProperty] = (), home: Path | None = None,
    client_env: Mapping[str, str] | None = None, env_dir: Path | None = None, interactive: bool = False,
) -> Isolation:  # fmt: skip
    """The container backend; ``persist`` writes the marker (ID + daemon identity) before start."""
    return _ContainerBackend(  # pyright: ignore[reportReturnType]
        settings, runner=runner, persist=persist, companions=companions, require=require,
        home=home if home is not None else Path.home(), client_env=client_env or {},
        env_dir=env_dir, interactive=interactive,
    )  # fmt: skip
