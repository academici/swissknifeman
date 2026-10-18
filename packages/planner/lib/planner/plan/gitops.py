"""Scoped operation commits, literal Git pathspecs and no post-commit plan writes."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
from fnmatch import fnmatchcase
from functools import lru_cache
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from . import settings, store, workspace
from .model import PlanError, parse_ref

GIT_TIMEOUT_S = 600   # a commit runs the hooks of the repository


def _git(repo: Path, *args: str, code: str = "GIT_FAILED", env: dict | None = None) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env, timeout=GIT_TIMEOUT_S)
    except OSError as exc:
        raise PlanError("GIT_UNAVAILABLE", str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise PlanError(code, f"git {args[0] if args else ''} did not finish in {GIT_TIMEOUT_S}s") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise PlanError(code, detail or "git command failed")
    return result.stdout


def _git_path(repo: Path, name: str) -> Path:
    path = Path(os.fsdecode(_git(repo, "rev-parse", "--git-path", name)).removesuffix("\n"))
    return path if path.is_absolute() else repo / path


def _target(plan: store.Plan, ref: str) -> tuple[dict, dict]:
    try:
        parsed = parse_ref(ref)
    except ValueError as exc:
        raise PlanError("REF_INVALID", str(exc)) from exc
    if parsed.plan or parsed.repo or parsed.kind not in ("item", "unit"):
        raise PlanError("REF_INVALID", "commit requires a local item or item/unit reference")
    item = plan.items.get(ref.split("/", 1)[0])
    target = item if parsed.kind == "item" else plan.units.get(ref)
    if item is None or target is None:
        raise PlanError("REF_UNKNOWN", f"unknown commit reference {ref!r}")
    return item, target


def _pattern(text: str, repo: Path, prefix: str) -> str:
    """Normalize ownership patterns without resolving symlink leaves or Git pathspec magic."""
    if not isinstance(text, str) or not text or "\0" in text:
        raise PlanError("PATH_INVALID", "commit paths must be non-empty strings without NUL")
    if text.startswith("@plan/"):
        text = prefix + "/" + text[6:]
    if text.startswith("/"):
        try:
            text = Path(text).relative_to(repo).as_posix() + ("/" if text.endswith("/") else "")
        except ValueError as exc:
            raise PlanError("PATH_INVALID", f"path is outside repository: {text!r}") from exc
    if ".." in text.split("/"):
        raise PlanError("PATH_INVALID", f"parent traversal is not allowed: {text!r}")
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or parts[0] == ".git":
        raise PlanError("PATH_INVALID", f"invalid repository path: {text!r}")
    return "/".join(parts) + ("/" if text.endswith("/") else "")


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return path.startswith(pattern)
    segments, wanted = path.split("/"), pattern.split("/")

    @lru_cache(None)
    def match(i: int, j: int) -> bool:
        if j == len(wanted):
            return i == len(segments)
        if wanted[j] == "**":
            return match(i, j + 1) or (i < len(segments) and match(i + 1, j))
        return i < len(segments) and fnmatchcase(segments[i], wanted[j]) and match(i + 1, j + 1)

    return match(0, 0)


def _plan_patterns(prefix: str, ref: str, role: str) -> tuple[list[str], list[str]]:
    """Plan files one operation owns (relative to the repository that holds the plan) and the runtime files it never owns."""
    item_id = ref.split("/", 1)[0]
    phase_id = item_id.split(".", 1)[0]
    patterns = [f"{prefix}/phases/{phase_id}/{item_id}.json", f"{prefix}/phases/{phase_id}/{item_id}/**",
                f"{prefix}/phases/{phase_id}/phase.json", f"{prefix}/plan.json", f"{prefix}/log.jsonl",
                f"{prefix}/artifacts/{item_id}/**", f"{prefix}/.gitattributes", f"{prefix}/.gitignore"]
    if role == "reviewer":
        patterns += [f"{prefix}/knowledge/**", f"{prefix}/artifacts/**"]
    excluded = [f"{prefix}/views/**", f"{prefix}/context/**", f"{prefix}/.lock", ".git/**"]
    return patterns, excluded


def _product_texts(ref: str, item: dict, target: dict) -> list[str]:
    return target.get("files", []) if "/" in ref else [f["path"] for f in item.get("task_files", [])]


def _allowed(plan: store.Plan, repo: Path, ref: str, role: str, item: dict, target: dict,
             paths: list[str]) -> tuple[list[str], list[str]]:
    """Ownership patterns of a plan that lives inside ``repo`` (the plan and its product share one repository)."""
    prefix = plan.root.resolve().relative_to(repo).as_posix()
    patterns, excluded = _plan_patterns(prefix, ref, role)
    if role != "reviewer":
        patterns += [_pattern(p, repo, prefix) for p in _product_texts(ref, item, target)]
    for path in paths:
        normalized = _pattern(path, repo, prefix)
        if role == "reviewer" and not normalized.startswith(prefix + "/"):
            raise PlanError("PATH_INVALID", "reviewer --path must stay inside the plan directory")
        patterns.append(normalized)
    return patterns, excluded


def _route(text: str, role: str, source: Path | None, plan_root: Path, ws_repo: Path, prefix: str) -> tuple[str, str]:
    """Which repository owns a path of a plan in the workspace: ``@plan/…`` and paths inside the plan directory belong to
    the workspace, any other path to the source repository (a reviewer owns plan files only)."""
    _pattern(text, ws_repo, prefix)  # NUL, parent traversal and emptiness are refused for every route
    if text.startswith("@plan/"):
        return "workspace", _pattern(text, ws_repo, prefix)
    if text.startswith("/"):
        try:
            Path(text).relative_to(plan_root)
        except ValueError:
            if source is None:
                raise PlanError("PATH_INVALID", "reviewer --path must stay inside the plan directory") from None
            return "source", _pattern(text, source, prefix)
        return "workspace", _pattern(text, ws_repo, prefix)
    normalized = _pattern(text, ws_repo, prefix)
    if normalized == prefix or normalized.startswith(prefix + "/"):
        return "workspace", normalized
    if role == "reviewer" or source is None:
        raise PlanError("PATH_INVALID", "reviewer --path must stay inside the plan directory")
    return "source", normalized


def _workspace_allowed(plan: store.Plan, source: Path | None, ws_repo: Path, ref: str, role: str, item: dict,
                       target: dict, paths: list[str]) -> tuple[list[str], list[str], list[str]]:
    """``(source patterns, workspace patterns, workspace excluded)`` of a plan that lives in the workspace."""
    prefix = plan.root.resolve().relative_to(ws_repo).as_posix()
    ws_patterns, ws_excluded = _plan_patterns(prefix, ref, role)
    src_patterns: list[str] = []
    texts = list(paths) if role == "reviewer" else [*_product_texts(ref, item, target), *paths]
    for text in texts:
        where, normalized = _route(text, role, source, plan.root.resolve(), ws_repo, prefix)
        (ws_patterns if where == "workspace" else src_patterns).append(normalized)
    return src_patterns, ws_patterns, ws_excluded


def _changes(raw: bytes) -> list[list[str]]:
    """A rename/copy group is indivisible: both destination and source must be owned."""
    fields = iter(raw.split(b"\0"))
    groups = []
    for entry in fields:
        if not entry or entry[:1] in (b"!", b"#"):
            continue
        kind = entry[:1]
        if kind == b"u":
            raise PlanError("GIT_CONFLICT", f"unmerged path: {os.fsdecode(entry.split(b' ', 10)[-1])!r}")
        if kind in (b"1", b"2"):
            pieces = entry.split(b" ", 8 if kind == b"1" else 9)
            if len(pieces) != (9 if kind == b"1" else 10):
                raise PlanError("GIT_FAILED", "invalid porcelain v2 record")
            group = [os.fsdecode(pieces[-1])]
            if kind == b"2":
                source = next(fields, None)
                if not source:
                    raise PlanError("GIT_FAILED", "rename record has no source path")
                group.append(os.fsdecode(source))
        elif kind == b"?":
            group = [os.fsdecode(entry[2:])]
        else:
            raise PlanError("GIT_FAILED", "unknown porcelain v2 record")
        groups.append(group)
    return groups


def _message(plan: store.Plan, ref: str, role: str, item: dict, target: dict, *, commit_type: str | None,
             scope: str | None, summary: str | None, trailers: list[str], actor: dict | None,
             identity: tuple = ()) -> str:
    settings = plan.plan.get("settings", {}).get("commit", {})
    kind = commit_type or {"executor": "feat", "fix": "fix", "reviewer": "docs"}[role]
    scope = scope or settings.get("scope") or plan.plan["id"].split("-", 2)[-1].lower()
    if not re.fullmatch(r"[a-z]+", kind) or not re.fullmatch(r"[A-Za-z0-9._/-]+", scope):
        raise PlanError("CONTENT_INVALID", "commit type must be lowercase letters; scope must be a single token")
    summary = " ".join((summary if summary is not None else target.get("title", ref)).splitlines()).strip()
    if not summary:
        raise PlanError("CONTENT_INVALID", "commit summary must not be empty")
    lines = [f"{kind}({scope}): {summary} ({plan.plan['short_id']}.{ref})", "",
             f"Plan: {plan.plan['id']}", f"Plan-Ref: {ref}", f"Plan-Role: {role}"]
    actor = actor or (item.get("result") or {}).get("executor") or plan.plan.get("authoring")
    if actor and actor.get("provider") and actor.get("model"):
        value = "/".join(str(actor[k]) for k in ("provider", "model", "effort") if actor.get(k))
        if "\n" in value or "\r" in value:
            raise PlanError("CONTENT_INVALID", "commit actor must be a single line")
        lines.append(f"Plan-Actor: {value}")
    for trailer in [*settings.get("trailers", []), *trailers]:
        if not re.fullmatch(r"[A-Za-z0-9-]+: [^\r\n\0]+", trailer):
            raise PlanError("CONTENT_INVALID", "trailers must be single lines: Key: value")
        protected = ("plan", "plan-ref", "plan-role", "plan-actor", *(t.split(":", 1)[0].lower() for t in identity))
        if trailer.split(":", 1)[0].lower() in protected:
            raise PlanError("CONTENT_INVALID", "identity trailers cannot be overridden")
        lines.append(trailer)
    lines += identity  # set by the engine (Plan-Project, Plan-Source-Commit of the workspace part)
    return "\n".join(lines) + "\n"


def _read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _restore(path: Path, content: bytes | None, mode: int | None = None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(content)
        if mode is not None:
            path.chmod(mode)


WORKSPACE_LOCK_TIMEOUT = 10.0  # seconds to wait for git.lock before the workspace part is reported as ``locked``
_LOCK_POLL = 0.05


class _GitLocked(Exception):
    """The workspace ``git.lock`` stayed held by another process for the whole wait."""


@contextmanager
def _workspace_git_lock(timeout: float, code: str):
    """``flock`` on ``workspace_state_dir(code)/git.lock``, the file the workspace module locks (invariant W7)."""
    folder = workspace.state_dir(code)
    folder.mkdir(parents=True, exist_ok=True)
    fd = os.open(folder / "git.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise _GitLocked() from None
                time.sleep(_LOCK_POLL)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def _ensure_not_busy(repo: Path) -> None:
    if any(_git_path(repo, marker).exists() for marker in
           ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply")):
        raise PlanError("GIT_BUSY", "finish the active Git merge, rebase or cherry-pick first")


def _identity_args(repo: Path) -> list[str]:
    """``-c user.name=… -c user.email=…`` for the settings the repository lacks, so a workspace commit never fails on a
    machine without a Git identity (the workspace module does the same)."""
    args = []
    for key, fallback in (("user.name", "skm-workspace"), ("user.email", "workspace@localhost")):
        try:
            known = _git(repo, "config", "--get", key, code="GIT_NO_CONFIG").strip()
        except PlanError:
            known = b""
        if not known:
            args += ["-c", f"{key}={fallback}"]
    return args


def _commit_part(repo: Path, patterns: list[str], excluded: list[str], message: str, *, attr_root: Path | None,
                 leave_outside: bool, dry_run: bool, allow_empty: bool = False, identity: bool = False) -> dict:
    """One scoped commit in ``repo``: the changed paths that match ``patterns`` and not ``excluded`` go through a private
    index. ``attr_root`` is the plan directory whose ``.gitattributes`` the part keeps current (``None``: the part holds no
    plan files). Returns ``{"sha", "paths", "paths_digest", "outside"}``; ``sha`` is ``None`` for a dry run or an empty
    selection (``allow_empty``, else ``NOTHING_TO_COMMIT``)."""
    _ensure_not_busy(repo)
    # Status index refreshes are optional: suppress them so refusals are byte-identical.
    groups = _changes(_git(repo, "--no-optional-locks", "status", "--porcelain=v2", "-z", "--untracked-files=all"))
    selected, outside = set(), set()
    for group in groups:
        allowed = all(any(_matches(p, pat) for pat in patterns)
                      and not any(_matches(p, pat) for pat in excluded) for p in group)
        (selected if allowed else outside).update(group)
    # A source recreated after a rename is also a separate untracked record.
    # Being outside in any group wins over ownership in another record.
    selected.difference_update(outside)
    attr = attr_root / ".gitattributes" if attr_root is not None else None
    attr_before = attr_mode = None
    needs_attributes = False
    if attr is not None:
        if attr.is_symlink():
            raise PlanError("PATH_INVALID", "plan .gitattributes must not be a symlink")
        attr_before = _read_optional(attr)
        attr_mode = attr.stat().st_mode if attr_before is not None else None
        try:
            needs_attributes = attr_before is None or store.GITATTRIBUTES not in attr_before.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise PlanError("CONTENT_INVALID", "plan .gitattributes must be valid UTF-8") from exc
        # An attribute file renamed outside the operation also remains untouched.
        needs_attributes = needs_attributes and attr.relative_to(repo).as_posix() not in outside
        if needs_attributes:
            selected.add(attr.relative_to(repo).as_posix())
    if outside and not leave_outside:
        raise PlanError("OUTSIDE_SCOPE", f"foreign dirty paths: {', '.join(repr(p) for p in sorted(outside))}; "
                        "use --leave-outside or --path and plan.py log --type deviation")
    if not selected and not allow_empty:
        raise PlanError("NOTHING_TO_COMMIT", "no changed paths are allowed for this operation")
    selected = sorted(selected)
    try:
        digest = sha256("\n".join(selected).encode("utf-8")).hexdigest()
    except UnicodeEncodeError as exc:
        raise PlanError("PATH_INVALID", "commit paths must be valid UTF-8") from exc
    result = {"sha": None, "paths": selected, "paths_digest": digest, "outside": sorted(outside)}
    if dry_run or not selected:
        return result
    index = _git_path(repo, "index")
    lock = index.with_name(index.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PlanError("GIT_FAILED", "Git index is locked by another operation") from exc
    os.close(fd)
    try:
        # Git owns a private index; the real lock serializes operations even across plans.
        # A failing hook/add/commit cannot change the caller's staged work.
        with tempfile.TemporaryDirectory(prefix="task-commit-", dir=index.parent) as tmp:
            private = Path(tmp) / "index"
            original_index = _read_optional(index)
            if original_index is not None:
                private.write_bytes(original_index)
                # Keep the original mtime: a fresh one defeats Git's racy-clean detection and a
                # same-size rewrite within one timestamp tick would be missed.
                st = index.stat()
                os.utime(private, ns=(st.st_atime_ns, st.st_mtime_ns))
            env = {**os.environ, "GIT_INDEX_FILE": str(private)}
            indexed = set(os.fsdecode(p) for p in _git(repo, "ls-files", "-z", env=env).split(b"\0") if p)
            # Already staged deletions (including rename sources) are absent from the index.
            add_paths = [p for p in selected if p in indexed or os.path.lexists(repo / p)]
            if needs_attributes and attr.relative_to(repo).as_posix() not in add_paths:
                add_paths.append(attr.relative_to(repo).as_posix())
            pathspec, addspec, msg = Path(tmp) / "paths", Path(tmp) / "add-paths", Path(tmp) / "message"
            pathspec.write_bytes(b"".join(os.fsencode(p) + b"\0" for p in selected))
            addspec.write_bytes(b"".join(os.fsencode(p) + b"\0" for p in add_paths))
            msg.write_text(message, encoding="utf-8")
            try:
                if needs_attributes:
                    store.ensure_gitattributes(attr_root)
                    if attr_mode is not None:
                        attr.chmod(attr_mode)
                if add_paths:
                    _git(repo, "--literal-pathspecs", "add", f"--pathspec-from-file={addspec}", "--pathspec-file-nul", env=env)
                who = _identity_args(repo) if identity else []
                _git(repo, *who, "--literal-pathspecs", "commit", "--only", f"--pathspec-from-file={pathspec}",
                     "--pathspec-file-nul", "-F", str(msg), env=env)
            except (PlanError, OSError):
                if needs_attributes:
                    _restore(attr, attr_before, attr_mode)
                raise
            # Same filesystem publication under the still-held real index lock.
            os.replace(private, index)
            result["sha"] = os.fsdecode(_git(repo, "rev-parse", "HEAD")).strip()
    finally:
        lock.unlink(missing_ok=True)
    return result


def _in_workspace(root: Path) -> tuple[str, str] | None:
    """``(workspace code, project code)`` when the plan directory lives in the portable workspace, else ``None`` (also for a bad environment:
    the legacy path must not start failing on it)."""
    try:
        return workspace.workspace_project_of(root)
    except ValueError:
        return None


def commit(plan_dir: str | Path, ref: str, *, role: str, paths: list[str] = (), leave_outside: bool = False,
           dry_run: bool = False, commit_type: str | None = None, scope: str | None = None,
           summary: str | None = None, trailers: list[str] = (), actor: dict | None = None) -> dict:
    """Commit precisely the changed paths of one operation; preflight precedes owned writes.

    A plan inside its checkout: one commit in that repository (plan files and product together). A plan in the portable
    workspace (D7): the product paths are committed in the source repository, then the plan files in the workspace
    repository under ``git.lock``, with ``Plan-Project`` and ``Plan-Source-Commit``; a failing workspace part never undoes the
    source commit.
    """
    if role not in ("executor", "reviewer", "fix"):
        raise PlanError("CONTENT_INVALID", "commit role must be executor, reviewer or fix")
    root = Path(plan_dir).resolve()
    _target(store.load_plan(root), ref)
    found = _in_workspace(root)
    if found is not None:
        project_id = found[1]
        return _commit_split(root, ref, project_id, role=role, paths=list(paths), leave_outside=leave_outside,
                             dry_run=dry_run, commit_type=commit_type, scope=scope, summary=summary,
                             trailers=list(trailers), actor=actor)
    repo = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel", code="GIT_UNAVAILABLE")).removesuffix("\n")).resolve()
    with store.PlanLock(root, timeout=float(settings.for_root(root.parent).get("lock.timeout_seconds"))):
        plan = store.load_plan(root)
        item, target = _target(plan, ref)
        _ensure_not_busy(repo)
        patterns, excluded = _allowed(plan, repo, ref, role, item, target, list(paths))
        message = _message(plan, ref, role, item, target, commit_type=commit_type, scope=scope,
                           summary=summary, trailers=list(trailers), actor=actor)
        part = _commit_part(repo, patterns, excluded, message, attr_root=root, leave_outside=leave_outside,
                            dry_run=dry_run)
        return {"sha": part["sha"], "ref": ref, "role": role, "paths": part["paths"],
                "paths_digest": part["paths_digest"], "outside": part["outside"], "message": message,
                "repo": "source", "workspace_sha": None, "workspace_commit": {"status": "skipped-legacy"}}


def _workspace_part(ws_repo: Path, plan: store.Plan, patterns: list[str], excluded: list[str], ref: str, role: str,
                    item: dict, target: dict, project_id: str, source_sha: str | None, *, dry_run: bool, root: Path,
                    commit_type: str | None, scope: str | None, summary: str | None, trailers: list[str],
                    actor: dict | None) -> dict:
    """Plan files of one operation in the workspace repository: ``{"status", "error"?, "sha", "paths", "outside",
    "paths_digest"}``. Never raises: a failure is a status, the source commit stays."""
    answer = {"status": "nothing", "sha": None, "paths": [], "paths_digest": sha256(b"").hexdigest(), "outside": []}
    if not (ws_repo / ".git").exists():
        answer["status"] = "skipped-no-git"
        return answer
    identity = (f"Plan-Project: {project_id}", *([f"Plan-Source-Commit: {source_sha}"] if source_sha else ()))
    try:
        message = _message(plan, ref, role, item, target, commit_type=commit_type, scope=scope, summary=summary,
                           trailers=trailers, actor=actor, identity=identity)

        def run() -> dict:
            # foreign dirty paths of the workspace (other plans, other projects) always stay out, never OUTSIDE_SCOPE
            return _commit_part(ws_repo, patterns, excluded, message, attr_root=root, leave_outside=True,
                                dry_run=dry_run, allow_empty=True, identity=True)

        if dry_run:
            part = run()
        else:
            with _workspace_git_lock(WORKSPACE_LOCK_TIMEOUT, ws_repo.name):
                part = run()
    except _GitLocked:
        answer["status"] = "locked"
        answer["error"] = f"WORKSPACE_GIT_LOCKED: another process holds the workspace git lock (waited {WORKSPACE_LOCK_TIMEOUT:g} s)"
        return answer
    except (PlanError, OSError, ValueError) as exc:
        answer["status"] = "failed"
        answer["error"] = f"{exc.code}: {exc.message}" if isinstance(exc, PlanError) else f"{exc.__class__.__name__}: {exc}"
        return answer
    answer.update(sha=part["sha"], paths=part["paths"], paths_digest=part["paths_digest"], outside=part["outside"])
    if part["sha"]:
        answer["status"] = "committed"
    elif part["paths"]:
        answer["status"] = "dry-run"  # the paths a real run would commit
    return answer


def _commit_split(root: Path, ref: str, project_id: str, *, role: str, paths: list[str], leave_outside: bool,
                  dry_run: bool, commit_type: str | None, scope: str | None, summary: str | None, trailers: list[str],
                  actor: dict | None) -> dict:
    ws_repo = workspace.workspace_root(_in_workspace(root)[0]).resolve()
    with store.PlanLock(root, timeout=float(settings.for_root(root.parent).get("lock.timeout_seconds"))):
        plan = store.load_plan(root)
        item, target = _target(plan, ref)
        source = None
        if role != "reviewer":  # a reviewer commits plan files only; the checkout is not needed
            source = Path(os.fsdecode(_git(plan.repo_root, "rev-parse", "--show-toplevel",
                                           code="GIT_UNAVAILABLE")).removesuffix("\n")).resolve()
            _ensure_not_busy(source)
        src_patterns, ws_patterns, ws_excluded = _workspace_allowed(plan, source, ws_repo, ref, role, item, target, paths)
        message = _message(plan, ref, role, item, target, commit_type=commit_type, scope=scope,
                           summary=summary, trailers=trailers, actor=actor)
        # refuse a spoofed Plan-Project/Plan-Source-Commit now, before the source commit; the workspace message repeats it
        _message(plan, ref, role, item, target, commit_type=commit_type, scope=scope, summary=summary,
                 trailers=trailers, actor=actor, identity=(f"Plan-Project: {project_id}", "Plan-Source-Commit: 0"))
        part = {"sha": None, "paths": [], "paths_digest": sha256(b"").hexdigest(), "outside": []}
        if source is not None:
            part = _commit_part(source, src_patterns, [".git/**"], message, attr_root=None,
                                leave_outside=leave_outside, dry_run=dry_run, allow_empty=True)
        ws = _workspace_part(ws_repo, plan, ws_patterns, ws_excluded, ref, role, item, target, project_id, part["sha"],
                             dry_run=dry_run, root=root, commit_type=commit_type, scope=scope, summary=summary,
                             trailers=trailers, actor=actor)
        if not part["paths"] and ws["status"] == "nothing":
            raise PlanError("NOTHING_TO_COMMIT", "no changed paths are allowed for this operation")
        primary = part if part["paths"] else ws
        workspace_commit = {"status": ws["status"], **({"error": ws["error"]} if "error" in ws else {})}
        return {"sha": primary["sha"], "ref": ref, "role": role, "paths": primary["paths"],
                "paths_digest": primary["paths_digest"], "outside": part["outside"], "message": message,
                "repo": "source" if primary is part else "workspace", "workspace_sha": ws["sha"],
                "workspace_commit": workspace_commit, "workspace_paths": ws["paths"],
                "workspace_outside": ws["outside"]}


_LOG_FORMAT = "%H%x1f%s%x1f" + "%x1f".join(
    f"%(trailers:key={key},valueonly,separator=%x1e)" for key in ("Plan", "Plan-Ref", "Plan-Role")) + "%x1e"


def _trailer(value: str) -> str:
    return value.replace("\x1e", "\n").strip().splitlines()[0] if value.strip() else ""


def list_commits(plan_dir: str | Path, ref: str | None = None, *, role: str | None = None) -> dict:
    """Read-only plan -> commits link: trailers in HEAD history, then legacy ``result.commits``. A plan in the workspace
    reads the history of its checkout (``Plan.source_root``); without one the list is empty and ``source_unbound`` is true."""
    plan = store.load_plan(Path(plan_dir).resolve())
    if ref is not None:
        try:
            parsed = parse_ref(ref)
        except ValueError as exc:
            raise PlanError("REF_INVALID", str(exc)) from exc
        if parsed.plan or parsed.repo or parsed.kind not in ("item", "unit"):
            raise PlanError("REF_INVALID", "commits requires a local item or item/unit reference")
        if ref.split("/", 1)[0] not in plan.items or (parsed.kind == "unit" and ref not in plan.units):
            raise PlanError("REF_UNKNOWN", f"unknown commit reference {ref!r}")
    if role is not None and role not in ("executor", "reviewer", "fix"):
        raise PlanError("CONTENT_INVALID", "commit role must be executor, reviewer or fix")
    rows: dict[str, dict] = {}
    history, unbound = plan.root, False
    if _in_workspace(plan.root) is not None:
        # the product commits live in the checkout of the project, not in the workspace repository
        history = plan.source_root
        unbound = history is None
    raw = b""  # no checkout / no repository / empty history: nothing to read, not an error
    if not unbound:
        try:
            raw = _git(history, "log", "-z", f"--format={_LOG_FORMAT}", code="GIT_FAILED")
        except PlanError as exc:
            if exc.code == "GIT_UNAVAILABLE":
                raise
    for record in raw.decode("utf-8", errors="replace").split("\0"):
        fields = record.strip("\n").rstrip("\x1e").split("\x1f")
        if len(fields) != 5:
            continue
        sha, subject, plan_id, commit_ref, commit_role = fields[0], fields[1], *map(_trailer, fields[2:])
        if plan_id != plan.plan["id"] or not commit_ref:
            continue
        if ref is not None and commit_ref != ref and not commit_ref.startswith(ref + "/"):
            continue
        if role is not None and commit_role != role:
            continue
        rows[sha] = {"sha": sha, "ref": commit_ref, "role": commit_role or None, "subject": subject,
                     "source": "trailer"}
    if role is None:
        for item_id, item in plan.items.items():
            if ref is not None and item_id != ref.split("/", 1)[0]:
                continue
            if ref is not None and "/" in ref:
                continue
            for sha in (item.get("result") or {}).get("commits", []):
                if not any(known.startswith(sha) or sha.startswith(known) for known in rows):
                    rows[sha] = {"sha": sha, "ref": item_id, "role": None, "subject": "", "source": "finish"}
    answer = {"plan": plan.plan["id"], "ref": ref, "commits": list(rows.values())}
    if unbound:
        answer["source_unbound"] = True
    return answer
