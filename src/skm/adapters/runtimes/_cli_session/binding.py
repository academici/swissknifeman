"""Bind a verified CLI launch to the exact bytes admitted by the control plane."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.runtimes.domain.capability import verification_context_key
from skm.modules.runtimes.domain.observation import ObservationBinding

from .launch import LaunchCommand
from .probe import resolve_binary_path

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import BinaryIO

    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.ids import Digest
    from skm.modules.runtimes.domain.request import AgentRequest

    from .runtime import ProbedCli

__all__: list[str] = []

_LANDLOCK_PYTHON_ARGS = ("-I", "-S")
_LANDLOCK_WRAPPER = Path(__file__).resolve().parents[2] / "sandbox" / "landlock_exec.py"


def _unavailable(request: AgentRequest, reason: str) -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        "Cannot bind the verified runtime launch",
        details={"runtime_id": request.runtime_id, "reason": reason},
    )


def verified_probe[P: ProbedCli](
    request: AgentRequest,
    probed: P | None,
    *,
    candidate: str,
    environ: Mapping[str, str],
    adapter_version: str,
    probe_config_digest: Digest,
) -> P:
    """Validate the worker's detection record without running CLI probe subprocesses."""
    context = request.verification_context
    if context is None:
        raise _unavailable(request, "verification_context_missing")
    if probed is None:
        raise _unavailable(request, "verified_runtime_not_probed")
    os_kernel = probed.cache_key.os_kernel
    if "/" not in os_kernel:
        os_kernel = os_kernel.replace(":", "/", 1)
    if (
        request.process_owner.host_id != context.host_id
        or request.isolation_profile != context.isolation_profile
        or adapter_version != context.adapter_version
        or probed.cache_key.adapter_version != context.adapter_version
        or probed.cache_key.launch_config_digest != probe_config_digest
        or os_kernel != f"{context.os}/{context.kernel}"
        or probed.binary_sha256 != context.binary_sha256
        or probed.version is None
        or probed.version != request.expected_runtime_version
        or (
            request.verification_key is not None
            and request.verification_key != verification_context_key(context)
        )
    ):
        raise _unavailable(request, "verification_context_mismatch")
    try:
        resolved = resolve_binary_path(candidate, environ=environ, display_name=request.runtime_id)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _unavailable(request, "verified_runtime_unavailable") from exc
    if resolved != Path(probed.binary_realpath):
        raise _unavailable(request, "verified_runtime_locator_changed")
    return probed


def canonical_launch_digest(template: object) -> Digest:
    encoded = json.dumps(template, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class _LaunchFile:
    path: Path
    digest: Digest
    header: bytes


def _copy_and_hash(source: BinaryIO, target: Path | None) -> tuple[Digest, bytes]:
    hasher = hashlib.sha256()
    header = source.read(256)
    hasher.update(header)
    if target is None:
        while chunk := source.read(65_536):
            hasher.update(chunk)
    else:
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o500), "wb") as snapshot:
            snapshot.write(header)
            while chunk := source.read(65_536):
                hasher.update(chunk)
                snapshot.write(chunk)
            os.fchmod(snapshot.fileno(), 0o500)
    return f"sha256:{hasher.hexdigest()}", header


def _read_launch_file(path: Path, *, workdir: Path, target: Path | None, executable: bool) -> _LaunchFile:
    if not path.is_absolute() or ".." in path.parts or path.is_relative_to(workdir):
        raise ValueError("launch sources must be absolute paths outside the worktree")
    resolved = path.resolve(strict=True)
    if resolved.is_relative_to(workdir):
        raise ValueError("resolved launch source is inside the worktree")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(resolved, flags), "rb") as src:
        mode = os.fstat(src.fileno()).st_mode
        if not stat.S_ISREG(mode) or (executable and not mode & 0o111):
            raise ValueError("launch source must be a regular executable file or wrapper")
        digest, header = _copy_and_hash(src, target)
    return _LaunchFile(resolved, digest, header)


def _shebang(header: bytes) -> tuple[Path, tuple[str, ...]]:
    # Linux passes the remainder of the shebang line as a single optional argument.
    line, newline, _ = header.partition(b"\n")
    parts = line[2:].strip(b" \t").split(None, 1)
    if not parts or (not newline and len(line) == 256) or any(byte in line for byte in b"\0\r\v\f"):
        raise ValueError("invalid shebang")
    interpreter = Path(os.fsdecode(parts[0]))
    if interpreter.name == "env":
        raise ValueError("PATH-dispatched shebangs cannot be bound")
    return interpreter, tuple(os.fsdecode(arg) for arg in parts[1:])


@dataclass(frozen=True, slots=True)
class _ExecutableBinding:
    command: WrappedCommand
    binary_path: Path
    directory: Path | None

    def _file(self, source: Path, name: str, *, executable: bool = True) -> _LaunchFile:
        return _read_launch_file(
            source,
            workdir=self.command.cwd,
            target=None if self.directory is None else self.directory / name,
            executable=executable,
        )

    def _interpreter(self, source: Path, name: str) -> _LaunchFile:
        if self.directory is not None:
            (self.directory / name).mkdir(mode=0o700)
        dependency = self._file(source, f"{name}/executable")
        if not dependency.header.startswith(b"\x7fELF") or dependency.path.name == "env":
            raise ValueError("launch interpreter must be a native executable with a fixed identity")
        if self.directory is not None and re.fullmatch(
            r"python(?:[23](?:\.\d+)?)?[td]?", dependency.path.name
        ):
            # CPython consults home to locate the standard library when launched from a copied binary.
            home = str(dependency.path.parent)
            if any(char in home for char in "\r\n"):
                raise ValueError("interpreter home cannot be written to pyvenv.cfg")
            config = self.directory / name / "pyvenv.cfg"
            with config.open("x", encoding="utf-8") as output:
                output.write(f"home = {home}\ninclude-system-site-packages = true\n")
        return dependency

    def capture(self) -> tuple[Digest, Digest, tuple[str, ...], tuple[str, ...]]:
        template = getattr(self.command, "verification_template", None)
        if template is None:
            raise ValueError("adapter did not render a verifiable launch template")
        argv = self.command.argv
        binary_index = 0
        if argv[1:4] == ("-P", "-m", "skm.adapters.sandbox.landlock_exec"):
            binary_index = argv.index("--") + 1
        if argv[binary_index] != str(self.binary_path):
            raise ValueError("rendered launch does not use the probed executable")

        binary = self._file(self.binary_path, self.binary_path.name)
        dependencies: dict[str, tuple[str, Digest]] = {}
        prefix = (str(self.binary_path),)
        if self.directory is not None:
            prefix = (str(self.directory / self.binary_path.name),)
        if binary.header.startswith(b"#!"):
            interpreter_path, options = _shebang(binary.header)
            interpreter = self._interpreter(interpreter_path, "shebang-interpreter")
            dependencies["shebang"] = (str(interpreter.path), interpreter.digest)
            if self.directory is not None:
                prefix = (str(self.directory / "shebang-interpreter/executable"), *options, *prefix)
        elif not binary.header.startswith(b"\x7fELF"):
            raise ValueError("verified runtime must be a native executable or a fixed-interpreter script")

        target_argv = (*prefix, *argv[binary_index + 1 :])
        if binary_index:
            interpreter = self._interpreter(Path(argv[0]), "landlock-interpreter")
            wrapper = self._file(_LANDLOCK_WRAPPER, "landlock_exec.py", executable=False)
            dependencies["landlock_interpreter"] = (str(interpreter.path), interpreter.digest)
            dependencies["landlock_wrapper"] = (str(wrapper.path), wrapper.digest)
            if self.directory is not None:
                target_argv = (
                    str(self.directory / "landlock-interpreter/executable"),
                    *_LANDLOCK_PYTHON_ARGS,
                    str(self.directory / "landlock_exec.py"),
                    *argv[4:binary_index],
                    *target_argv,
                )
        digest = canonical_launch_digest(
            {
                "template": template,
                "dependencies": dependencies,
                **({"interpreter_layout": "pyvenv-home-v1"} if dependencies else {}),
                "landlock_python_args": _LANDLOCK_PYTHON_ARGS if binary_index else (),
            }
        )
        return digest, binary.digest, target_argv, prefix


def launch_verification_digest(command: WrappedCommand, binary_path: str) -> Digest:
    """Measure the rendered template and executable dependencies for canary evidence."""
    digest, _, _, _ = _ExecutableBinding(command, Path(binary_path), None).capture()
    return digest


@dataclass(frozen=True, slots=True)
class _BoundLaunchCommand(LaunchCommand):
    exec_bound: bool = True


def bind_launch(
    request: AgentRequest, probed: ProbedCli, command: WrappedCommand, step_dir: Path
) -> tuple[WrappedCommand, tuple[str, ...] | None]:
    context = request.verification_context
    if context is None:
        return command, None
    directory = step_dir / ".pinned-bin"
    created = False
    try:
        client_home = None if request.client_home is None else Path(request.client_home).resolve()
        if (
            directory.is_relative_to(command.cwd)
            or (client_home is not None and directory.is_relative_to(client_home))
            or any(
                rule.root != "*" and directory.is_relative_to(Path(rule.root).resolve())
                for rule in request.permissions.fs_write.allow
            )
        ):
            raise ValueError("the executable snapshot overlaps a writable root")
        if any(name.startswith(("LD_", "DYLD_")) or name == "PYTHONHOME" for name in command.env):
            raise ValueError("verified launch cannot override the host loader")
        directory.mkdir(mode=0o700)
        created = True
        binding = _ExecutableBinding(command, Path(probed.binary_realpath), directory)
        digest, binary_digest, argv, prefix = binding.capture()
        if binary_digest != context.binary_sha256:
            raise _unavailable(request, "verified_runtime_binary_changed")
        if digest != context.launch_config_digest:
            raise _unavailable(request, "verified_launch_config_changed")
        return _BoundLaunchCommand(argv, command.env, command.cwd, command.ownership).as_wrapped(), prefix
    except (CapabilityUnavailable, OSError, RuntimeError, ValueError) as exc:
        error = (
            exc
            if isinstance(exc, CapabilityUnavailable)
            else _unavailable(request, "verified_executable_snapshot_failed")
        )
        if created:
            try:
                shutil.rmtree(directory)
            except OSError as cleanup:
                error.add_note(f"snapshot cleanup failed: {cleanup}")
        if error is exc:
            raise
        raise error from exc


def bind_observation(request: AgentRequest, probed: ProbedCli, adapter_version: str) -> ObservationBinding:
    verified = request.verification_context is not None
    return ObservationBinding(
        runtime_id=request.runtime_id,
        runtime_version=probed.version,
        adapter_version=adapter_version,
        executable_sha256=probed.binary_sha256,
        verification_key=request.verification_key if verified else None,
        provider_reported_model=None,
        model_source="unavailable",
    )
