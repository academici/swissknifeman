"""``apply``: the critical section of the plans migration (contract ``workspace-contract#migration`` steps 1-8, invariants W2-W5).

Under the migration lock of the project and the ``PlanLock`` of every v4 plan of the source (taken in the order of the
sorted folder paths) the bridge

1. recomputes the digest of the source and compares it with the manifest of ``inspect`` (``MIGRATION_SOURCE_CHANGED``);
2. decides per folder what to do with the workspace copy (copied, skipped-equal, imported-copy, kept-workspace);
3. copies what has to move to ``<workspace>/.staging/<op_id>`` (``shutil.copy2``, no symlink followed) and compares the digest
   of every copy with the manifest;
4. verifies the staged v4 plans (``verify``: loadable, no ``check`` error the source does not have);
5. moves them with ``os.rename`` (staging is inside the workspace, so on its volume): the whole ``plans`` folder when the
   workspace has none yet, otherwise folder by folder into absent targets;
6. writes the project marker ``plans_store = workspace`` (atomic) while still holding every lock.

Any failure before the rename removes the staging folder and leaves the marker as it was; the refusal names the ``phase``
it stopped at. A repeated call after a rename that was not followed by the marker finds the folders with the digest of the
manifest and only writes the marker; a call with the marker already at ``workspace`` and equal copies is a ``noop``.

Answers carry paths relative to ``plans/``, sizes and digests, never file content or an absolute path.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Dict, List, Optional

import inspector
import partners
import verify

PHASES = ("request", "lock", "digest", "plan", "copy", "verify", "rename", "marker", "done")
ENV_FAIL_AT = "SKM_MIGRATOR_FAIL_AT"  # tests only: pre-rename | post-rename | copy
_OP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_DEVICE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_PROJECT_ID = re.compile(r"^prj_[0-9A-HJKMNP-TV-Z]{26}$")
_ACTIONS = {"copy": "copied", "equal": "skipped-equal", "import": "imported-copy", "keep": "kept-workspace"}
DEFAULT_LOCK_TIMEOUT_S = 30.0


class Refusal(Exception):
    """A refusal with a stable code; ``phase`` is the step it stopped at, ``details`` extra fields of the answer."""

    def __init__(self, code: str, message: str, phase: str, **details):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.phase = phase
        self.details = details

    def as_output(self) -> Dict[str, object]:
        output: Dict[str, object] = {"result": "refused", "code": self.code, "message": self.message,
                                     "phase": self.phase}
        output.update(self.details)
        return output


class Unit:
    """One folder to move: a plan folder or the loose files (``_root``)."""

    def __init__(self, entry: dict):
        self.name: str = entry["name"]
        self.cls: str = entry["class"]
        self.files: List[dict] = entry["files"]
        self.bytes: int = entry["bytes"]
        self.digest: str = entry["digest"]
        self.prefix: str = entry["prefix"]
        self.action = "copy"
        self.stored_as = entry["name"]  # the name in the workspace (a device suffix on an imported copy)

    @property
    def kind_dir(self) -> str:
        return "plans" if self.cls == "v4" else "legacy-plans"

    @property
    def stage_rel(self) -> str:
        return f"{self.kind_dir}/{self.name}"

    @property
    def target_rel(self) -> str:
        return f"{self.kind_dir}/{self.stored_as}"

    def result(self) -> Dict[str, object]:
        row: Dict[str, object] = {"name": self.name, "class": self.cls, "action": _ACTIONS[self.action],
                                  "files": len(self.files), "bytes": self.bytes, "digest": self.digest}
        if self.stored_as != self.name:
            row["stored_as"] = self.stored_as
        return row


# --------------------------------------------------------------------------------------------------- request

def _text(request: dict, key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value:
        raise Refusal("INPUT_INVALID", f"{key} must be a non-empty string", "request")
    return value


def _folder(request: dict, key: str) -> Path:
    path = Path(_text(request, key))
    if not path.is_absolute() or not path.is_dir():
        raise Refusal("INPUT_INVALID", f"{key} must be an existing absolute folder", "request")
    return path


def parse(request: dict) -> Dict[str, object]:
    project_root = _folder(request, "project_root")
    workspace_root = _folder(request, "workspace_root")
    project_id = _text(request, "project_id")
    op_id = _text(request, "op_id")
    if not _PROJECT_ID.match(project_id):
        raise Refusal("INPUT_INVALID", "project_id must look like prj_ and 26 Crockford base32 characters", "request")
    if not _OP_ID.match(op_id):
        raise Refusal("INPUT_INVALID", "op_id must be 1-64 letters, digits, '_' or '-'", "request")
    manifest = request.get("manifest")
    if (not isinstance(manifest, dict) or not isinstance(manifest.get("plans"), list)
            or not isinstance(manifest.get("top_level"), list) or not isinstance(manifest.get("digest"), str)):
        raise Refusal("INPUT_INVALID", "manifest must be the answer of inspect", "request")
    mode = request.get("mode", "initial")
    if mode not in ("initial", "import"):
        raise Refusal("INPUT_INVALID", "mode must be initial or import", "request")
    on_conflict = request.get("on_conflict")
    if on_conflict not in (None, "keep-workspace", "import-copy"):
        raise Refusal("INPUT_INVALID", "on_conflict must be null, keep-workspace or import-copy", "request")
    device_short = request.get("device_short")
    if device_short is not None and (not isinstance(device_short, str) or not _DEVICE.match(device_short)):
        raise Refusal("INPUT_INVALID", "device_short must be 1-16 letters or digits", "request")
    timeout = request.get("lock_timeout_s", DEFAULT_LOCK_TIMEOUT_S)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
        raise Refusal("INPUT_INVALID", "lock_timeout_s must be a non-negative number", "request")
    return {"project_root": project_root, "workspace_root": workspace_root, "project_id": project_id, "op_id": op_id,
            "manifest": manifest, "mode": mode, "on_conflict": on_conflict, "device_short": device_short,
            "timeout": float(timeout)}


# ------------------------------------------------------------------------------------------------ helpers

def _phase(state: Dict[str, str], phase: str, progress) -> None:
    state["phase"] = phase
    if progress is not None and phase != "done":
        progress(f"phase {phase}")


def _fail_point(name: str) -> None:
    if os.environ.get(ENV_FAIL_AT) == name:
        raise RuntimeError(f"injected failure at {name}")


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _is_empty_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and not any(path.iterdir())


def _check_unique(units: List[Unit]) -> None:
    seen = set()
    for unit in units:
        if unit.stage_rel in seen:
            raise Refusal("MIGRATION_SOURCE_CHANGED", f"two folders are named {unit.name}", "digest")
        seen.add(unit.stage_rel)


@contextlib.contextmanager
def migration_lock(project_id: str):
    """``flock`` on ``<workspace state>/migrate-<project_id>.lock``: a second migration of the project is refused."""
    from aicore.state.locations import ensure_dir, workspace_state_dir
    directory = ensure_dir(workspace_state_dir())
    handle = open(directory / f"migrate-{project_id}.lock", "a+")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refusal("MIGRATION_LOCKED", "another migration of this project is running", "lock",
                          locked=[f"migrate-{project_id}"]) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


def lock_plans(stack: contextlib.ExitStack, plans: Path, names: List[str], timeout: float) -> None:
    """``PlanLock`` of every named v4 plan, in the order of the sorted folder paths; the stack releases them in reverse
    order. A plan that is held for longer than ``timeout`` is ``MIGRATION_LOCKED`` with the plan's name."""
    store = partners.planner_engine("plan.store")
    for name in sorted(names, key=lambda item: str(plans / item)):
        folder = plans / name
        if not (folder / "plan.json").is_file() or folder.is_symlink():
            raise Refusal("MIGRATION_SOURCE_CHANGED", f"plan {name} is gone from the source; run plan again", "lock")
        try:
            stack.enter_context(store.PlanLock(folder, timeout=timeout))
        except store.PlanError as exc:
            if exc.code == "PLAN_LOCKED":
                raise Refusal("MIGRATION_LOCKED", f"plan {name} is held by another process", "lock",
                              locked=[name]) from None
            if exc.code == "PLANS_MIGRATED":
                raise Refusal("MIGRATION_ALREADY_APPLIED", "the project marker already points at the workspace",
                              "lock") from None
            raise Refusal("MIGRATION_FAILED", f"plan {name}: {exc.code}", "lock") from None


def _compare_source(manifest: dict, fresh: dict) -> None:
    """``MIGRATION_SOURCE_CHANGED`` with the names of the folders that differ from the manifest."""
    if fresh["digest"] == manifest["digest"]:
        return
    known = {plan.get("name"): plan.get("digest") for plan in manifest["plans"] if isinstance(plan, dict)}
    now = {plan["name"]: plan["digest"] for plan in fresh["plans"]}
    changed = {name for name in set(known) | set(now) if known.get(name) != now.get(name)}
    before = {(item.get("path"), item.get("sha256")) for item in manifest["top_level"] if isinstance(item, dict)}
    if before != {(item["path"], item["sha256"]) for item in fresh["top_level"]}:
        changed.add(inspector.ROOT_NAME)
    raise Refusal("MIGRATION_SOURCE_CHANGED", "the source changed since the plan; run plan again", "digest",
                  changed=sorted(changed))


def _copy_unit(unit: Unit, plans: Path, staging: Path, ticker: inspector.Ticker, counter: List[int]) -> None:
    destination = staging / unit.stage_rel
    destination.mkdir(parents=True, exist_ok=True)
    for entry in unit.files:
        source = plans / entry["path"]
        try:
            info = os.lstat(source)
        except OSError:
            raise Refusal("MIGRATION_SOURCE_CHANGED", f"{entry['path']} is gone from the source", "copy") from None
        if stat.S_ISLNK(info.st_mode):
            raise Refusal("MIGRATION_BLOCKED_SYMLINK", "a symlink appeared in the source", "copy",
                          symlinks=[entry["path"]])
        if not stat.S_ISREG(info.st_mode):
            raise Refusal("MIGRATION_SOURCE_CHANGED", f"{entry['path']} is not a regular file any more", "copy")
        target = destination / entry["path"][len(unit.prefix):]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
        counter[0] += 1
        ticker.tick(f"copied {counter[0]} files")
    if inspector.scan_digest(destination, unit.cls) != unit.digest:
        raise Refusal("MIGRATION_COPY_MISMATCH", f"the copy of {unit.name} differs from the manifest", "copy",
                      paths=[unit.name])


# ------------------------------------------------------------------------------------------------- planning

def _target_digest(project_dir: Path, unit: Unit, relative: str, progress) -> Optional[str]:
    target = project_dir / relative
    if not _exists(target):
        return None
    if target.is_symlink() or not target.is_dir():
        return "sha256:not-a-folder"
    return inspector.scan_digest(target, unit.cls, progress)


def decide(units: List[Unit], project_dir: Path, request: dict, progress) -> List[str]:
    """Set ``action`` and ``stored_as`` of every unit from the workspace copy; returns the names that conflict."""
    conflicts: List[str] = []
    suffix = request["device_short"]
    for unit in units:
        found = _target_digest(project_dir, unit, unit.target_rel, progress)
        if found is None:
            unit.action = "copy"
        elif found == unit.digest:
            unit.action = "equal"
        elif request["on_conflict"] == "keep-workspace":
            unit.action = "keep"
        elif unit.cls == "v4" and request["on_conflict"] is None:
            conflicts.append(unit.name)
        else:  # import-copy for a plan, the device suffix for opaque folders (contract step 6)
            if not suffix:
                raise Refusal("INPUT_INVALID", "device_short is required to import a copy next to a different folder",
                              "plan")
            unit.stored_as = f"{unit.name}~{suffix}"
            again = _target_digest(project_dir, unit, unit.target_rel, progress)
            if again is None:
                unit.action = "import"
            elif again == unit.digest:
                unit.action = "equal"
            else:
                conflicts.append(unit.name)
    return conflicts


# -------------------------------------------------------------------------------------------------- phases

def _verify_staged(units: List[Unit], plans: Path, staging: Path) -> None:
    failed = []
    for unit in units:
        if unit.cls != "v4" or unit.action not in ("copy", "import"):
            continue
        copy = verify.check_plan(staging / unit.stage_rel, unbound=True)
        base = verify.check_plan(plans / unit.name)
        fresh = verify.new_errors(base, copy)
        if not copy["loaded"] or copy["problems"] or fresh:
            failed.append({"name": unit.name, "loaded": copy["loaded"],
                           "problems": [{"file": f, "message": m} for f, m in copy["problems"]],
                           "new_errors": [{"code": c, "where": w} for c, w in fresh]})
    if failed:
        raise Refusal("MIGRATION_VERIFY_FAILED", f"{len(failed)} staged plan(s) do not verify", "verify", plans=failed)


def _rename(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(source, destination)
    except OSError as exc:
        raise Refusal("MIGRATION_TRANSFER_FAILED", f"cannot move a folder into the workspace: "
                      f"{exc.strerror or exc.__class__.__name__}", "rename") from None


def _transfer(units: List[Unit], staging: Path, project_dir: Path, progress) -> None:
    plans_target = project_dir / "plans"
    whole = not _exists(plans_target) or _is_empty_dir(plans_target)
    moving = [unit for unit in units if unit.action in ("copy", "import")]
    if whole:
        if _is_empty_dir(plans_target):
            plans_target.rmdir()
        (staging / "plans").mkdir(parents=True, exist_ok=True)
        _rename(staging / "plans", plans_target)
        moving = [unit for unit in moving if unit.cls != "v4"]
    else:
        for unit in moving:
            if unit.cls == "v4":
                _rename(staging / unit.stage_rel, project_dir / unit.target_rel)
        moving = [unit for unit in moving if unit.cls != "v4"]
    for unit in moving:
        _rename(staging / unit.stage_rel, project_dir / unit.target_rel)
    for unit in units:  # W4: the bytes after the rename are the bytes of the manifest
        if unit.action in ("copy", "import"):
            if inspector.scan_digest(project_dir / unit.target_rel, unit.cls, progress) != unit.digest:
                raise Refusal("MIGRATION_COPY_MISMATCH", f"{unit.name} differs from the manifest after the move",
                              "rename", paths=[unit.name])


def _plans_marker(request: dict):
    from aicore import workspace as aicore_workspace
    try:
        marker = aicore_workspace.read_marker(request["project_root"])
    except aicore_workspace.WorkspaceError as exc:
        raise Refusal("PROJECT_MARKER_INVALID", exc.message, "request") from None
    if marker is not None and marker["project_id"] != request["project_id"]:
        raise Refusal("PROJECT_MARKER_MISMATCH", "the marker of the checkout names another project", "request")
    return marker


def _manifest_units(manifest: dict) -> List[Unit]:
    try:
        return [Unit(entry) for entry in inspector.units_of(manifest)]
    except (KeyError, TypeError):
        raise Refusal("INPUT_INVALID", "manifest must be the answer of inspect", "request") from None


def _already_switched(request: dict, project_dir: Path, progress) -> Dict[str, object]:
    """The marker already points at the workspace: ``noop`` when every folder of the manifest is there with its digest."""
    units = _manifest_units(request["manifest"])
    different = []
    for unit in units:
        if _target_digest(project_dir, unit, unit.target_rel, progress) != unit.digest:
            different.append(unit.name)
        unit.action = "equal"
    if different:
        raise Refusal("MIGRATION_ALREADY_APPLIED", "the project marker points at the workspace and its copy differs "
                      "from the manifest", "done", paths=sorted(different))
    return {"result": "noop", "phase": "done", "mode": request["mode"], "op_id": request["op_id"],
            "plans": [unit.result() for unit in units]}


def _apply(request: dict, progress, state: Dict[str, str]) -> Dict[str, object]:
    from aicore import workspace as aicore_workspace
    project_root, workspace_root = request["project_root"], request["workspace_root"]
    plans = project_root / "plans"
    project_dir = workspace_root / "projects" / request["project_id"]
    staging = workspace_root / ".staging" / request["op_id"]
    marker = _plans_marker(request)
    if marker is not None and marker["plans_store"] == "workspace":
        return _already_switched(request, project_dir, progress)
    structure = inspector.inspect(project_root, hash_files=False)
    if structure["symlinks"]:
        raise Refusal("MIGRATION_BLOCKED_SYMLINK", "the source holds symlinks", "digest",
                      symlinks=structure["symlinks"])
    names = [plan["name"] for plan in request["manifest"]["plans"] if isinstance(plan, dict) and plan.get("class") == "v4"]
    _phase(state, "lock", progress)
    with migration_lock(request["project_id"]), contextlib.ExitStack() as locks:
        lock_plans(locks, plans, names, request["timeout"])
        _phase(state, "digest", progress)
        fresh = inspector.inspect(project_root, progress)
        if fresh["symlinks"]:
            raise Refusal("MIGRATION_BLOCKED_SYMLINK", "the source holds symlinks", "digest", symlinks=fresh["symlinks"])
        _compare_source(request["manifest"], fresh)
        units = [Unit(entry) for entry in inspector.units_of(fresh)]
        _check_unique(units)
        _phase(state, "plan", progress)
        conflicts = decide(units, project_dir, request, progress)
        if conflicts:
            raise Refusal("MIGRATION_CONFLICT", f"{len(conflicts)} plan(s) differ from the workspace; choose "
                          "--on-conflict keep-workspace or import-copy", "plan", conflicts=sorted(conflicts))
        _phase(state, "copy", progress)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        state["staged"] = "yes"
        ticker, counter = inspector.Ticker(progress), [0]
        for index, unit in enumerate(units):
            if unit.action in ("copy", "import"):
                _copy_unit(unit, plans, staging, ticker, counter)
                if index == 0:
                    _fail_point("copy")
        _phase(state, "verify", progress)
        _verify_staged(units, plans, staging)
        _phase(state, "rename", progress)
        _fail_point("pre-rename")
        _transfer(units, staging, project_dir, progress)
        _fail_point("post-rename")
        _phase(state, "marker", progress)
        aicore_workspace.write_marker(project_root, request["project_id"], "workspace")
        _phase(state, "done", progress)
    return {"result": "applied", "phase": "done", "mode": request["mode"], "op_id": request["op_id"],
            "plans": [unit.result() for unit in units]}


def run(request: dict, progress=inspector.stderr_progress) -> Dict[str, object]:
    """The ``apply`` answer: ``applied``, ``noop`` or a refusal (``result: refused``, ``code``, ``message``, ``phase``)."""
    state = {"phase": "request", "staged": ""}
    try:
        parsed = parse(request)
        staging = parsed["workspace_root"] / ".staging" / parsed["op_id"]
    except Refusal as refusal:
        return refusal.as_output()
    try:
        return _apply(parsed, progress, state)
    except Refusal as refusal:
        return refusal.as_output()
    except Exception as exc:  # noqa: BLE001 - a failed migration answers with its phase; nothing is left half-done
        return Refusal("MIGRATION_FAILED", f"{exc.__class__.__name__}: {getattr(exc, 'strerror', None) or 'see the log of the bridge'}",
                       state["phase"]).as_output()
    finally:
        if state["staged"]:  # only the folder this call made: a second call must not remove the staging of the first
            shutil.rmtree(staging, ignore_errors=True)
