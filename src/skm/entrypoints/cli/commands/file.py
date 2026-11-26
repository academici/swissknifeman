"""``skm file`` (cli §6.7, artifacts §5-§10): upload, inspect, cat, trash and restore files."""

from __future__ import annotations

import argparse
import base64
import errno
import os
import stat
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_view
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import Column, kv_lines, render, render_page, render_table
from skm.entrypoints.cli.refs import RefForm, RefKind, as_uuid, parse_ref
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.pagination import Page, validate_cursor
from skm.kernel.ports_uow import Surface
from skm.modules.artifacts import public as artifacts
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.safe_paths import UnsafePathError

if TYPE_CHECKING:
    from uuid import UUID

    from skm.application_bus.client import UploadedBlob
    from skm.entrypoints.cli.context import CliContext

__all__ = ["GROUP", "register", "resolve_file_id", "resolve_file_version_id"]

_CHUNK_BYTES: Final = 65536
_OPEN_FLAGS: Final = (
    os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
)
_HELP: Final = {
    "add": "upload a local file and register version 1",
    "version": "upload a new version for an existing file",
    "list": "list files in the active workspace or project",
    "show": "show file metadata and version history",
    "versions": "list versions of a file",
    "cat": "stream bytes of a file or file version",
    "trash": "move an active file to trash",
    "restore": "restore a trashed file",
}


def _symlink_error() -> ValidationFailed:
    msg = "symbolic links cannot be uploaded"
    finding: JsonObject = {"rule": "CS-SYMLINK", "level": "block", "message": msg, "location": None}
    return ValidationFailed(
        ErrorCode.CONTENT_UNSAFE,
        "content safety blocked upload",
        details={"reason": "not_acknowledged", "findings": [finding]},
    )


def _lstat_source(target: Path, raw_path: str) -> os.stat_result:
    try:
        return os.lstat(target)
    except FileNotFoundError as exc:
        raise NotFound(
            ErrorCode.NOT_FOUND, f"upload source not found: {raw_path}", details={"path": raw_path}
        ) from exc


@contextmanager
def _open_local_upload(path_text: str) -> Generator[tuple[str, int, Iterator[bytes]]]:
    if "\x00" in path_text:
        raise UnsafePathError(Path(path_text.replace("\x00", "")), "nul")
    raw_path = Path(path_text)
    raw_name = os.path.basename(path_text.rstrip("/\\")) or raw_path.name or path_text
    anchored = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path
    cur = Path(anchored.anchor)
    for part in anchored.parts[1:-1]:
        cur = cur / part
        if stat.S_ISLNK(_lstat_source(cur, path_text).st_mode):
            raise _symlink_error()
    lst = _lstat_source(anchored, path_text)
    if stat.S_ISLNK(lst.st_mode):
        raise _symlink_error()
    if not stat.S_ISREG(lst.st_mode):
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "upload source must be a regular file")
    fd: int | None = None
    try:
        try:
            fd = os.open(anchored, _OPEN_FLAGS)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise _symlink_error() from exc
            raise
        fst = os.fstat(fd)
        if not os.path.samestat(lst, fst) or not stat.S_ISREG(fst.st_mode):
            raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "upload source must be a regular file")

        def _chunks() -> Iterator[bytes]:
            assert fd is not None  # noqa: S101
            while chunk := os.read(fd, _CHUNK_BYTES):
                yield chunk

        yield raw_name, fst.st_size, _chunks()
    finally:
        if fd is not None:
            os.close(fd)


def _stage_local(
    ctx: CliContext, ws_id: WorkspaceId, path: str, media_type: str | None
) -> tuple[str, UploadedBlob, dict[str, Any]]:
    with _open_local_upload(path) as (orig, size_bytes, chunks):
        s = ctx.client.upload_blob(ws_id, chunks, size=size_bytes, media_type=media_type)
    blob = {
        "staged_blob_id": str(s.staged_blob_id),
        "workspace_id": str(s.workspace_id),
        "digest": s.digest,
        "size": s.size,
        "media_type": s.media_type,
    }
    return orig, s, blob


def _try_host_upload(ctx: CliContext, payload: JsonObject) -> JsonObject | None:
    try:
        host_ctx = build_host_context(ctx)
    except CapabilityUnavailable:
        return None
    ops = (op for m in MANIFESTS if m.id == "artifacts" for op in m.host_operations)
    spec = next((op for op in ops if op.name == "artifacts.host.upload_file"), None)
    if spec is None or Surface.CLI not in spec.surfaces:
        raise InternalError(ErrorCode.INTERNAL_ERROR, "artifacts.host.upload_file not registered for CLI")
    try:
        return cast("JsonObject", spec.run(host_ctx, payload))
    except CapabilityUnavailable as exc:
        if exc.details.get("port") == "UploadSourceReader":
            return None
        raise


def _resolve_scope(
    ctx: CliContext, proj_ref: str | None, ws_ref: str | None, *, default_project: bool
) -> tuple[WorkspaceId, ProjectId | None]:
    explicit_ws = resolve_workspace_id(ctx, ws_ref) if ws_ref is not None else None
    if proj_ref is not None:
        proj = resolve_project_view(ctx, proj_ref, workspace_ref=ws_ref)
        proj_ws = WorkspaceId(proj.workspace_id)
        if explicit_ws is not None and explicit_ws != proj_ws:
            raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "project does not belong to workspace")
        return proj_ws, ProjectId(proj.project_id)
    if explicit_ws is not None or not default_project:
        return explicit_ws or resolve_workspace_id(ctx, None), None
    try:
        proj = resolve_project_view(ctx, None)
        return WorkspaceId(proj.workspace_id), ProjectId(proj.project_id)
    except NotFound:
        return resolve_workspace_id(ctx, None), None


def _paginate[T](
    fetch: Callable[[str | None], tuple[Sequence[T], str | None]], *, after: str | None, fetch_all: bool
) -> Page[T]:
    items: list[T] = []
    cursor = after
    while True:
        batch, nxt = fetch(cursor)
        items.extend(batch)
        if not fetch_all or nxt is None:
            return Page(items=tuple(items), next=None if fetch_all or nxt is None else validate_cursor(nxt))
        cursor = nxt


def _list_all_files(
    ctx: CliContext, ws_id: WorkspaceId, proj_id: ProjectId | None
) -> Sequence[artifacts.FileSummaryView]:
    def _step(cur: str | None) -> tuple[Sequence[artifacts.FileSummaryView], str | None]:
        res: Any = ctx.client.ask(artifacts.ListFiles(ws_id, proj_id, after=cur, limit=100))
        return res.items, res.next

    return _paginate(_step, after=None, fetch_all=True).items


def _list_all_versions(ctx: CliContext, file_id: artifacts.FileId) -> Sequence[artifacts.FileVersionView]:
    def _step(cur: str | None) -> tuple[Sequence[artifacts.FileVersionView], str | None]:
        res: Any = ctx.client.ask(artifacts.ListFileVersions(file_id, cur, 100))
        return res.items, res.next

    return _paginate(_step, after=None, fetch_all=True).items


def _checked_file(
    ctx: CliContext, fid: artifacts.FileId, *, project_ref: str | None, workspace_ref: str | None
) -> artifacts.GetFileView:
    view = cast("artifacts.GetFileView", ctx.client.ask(artifacts.GetFile(file_id=fid)))
    ws_ok = workspace_ref is None or WorkspaceId(view.workspace_id) == resolve_workspace_id(
        ctx, workspace_ref
    )
    proj_ok = project_ref is None or (
        view.project_id == resolve_project_view(ctx, project_ref, workspace_ref=workspace_ref).project_id
    )
    if not (ws_ok and proj_ok):
        raise NotFound(ErrorCode.NOT_FOUND, "file not found", details={"kind": "file"})
    return view


def _pick_prefix[T](items: Sequence[T], id_of: Callable[[T], UUID], needle: str, kind: str, raw: str) -> UUID:
    hits = [id_of(it) for it in items if id_of(it).hex.lower().startswith(needle)]
    if not hits:
        raise NotFound(ErrorCode.NOT_FOUND, f"{kind} not found: {raw}", details={"kind": kind, "ref": raw})
    if len(hits) > 1:
        msg = f"ambiguous {kind}: {raw}"
        raise ValidationFailed(
            ErrorCode.AMBIGUOUS_REFERENCE, msg, details={"candidates": [str(h) for h in hits]}
        )
    return hits[0]


def resolve_file_id(
    ctx: CliContext, raw: str, *, project_ref: str | None = None, workspace_ref: str | None = None
) -> artifacts.FileId:
    """Resolve ``file:<uuid>``, bare ``<uuid>`` or ``>=8`` hex prefix to ``FileId``."""
    direct = as_uuid(raw)
    if direct is not None:
        return artifacts.FileId(direct)
    parsed = parse_ref(RefKind.FILE, raw)
    if parsed.form is RefForm.UUID and parsed.uuid is not None:
        return artifacts.FileId(parsed.uuid)
    ws_id, proj_id = _resolve_scope(ctx, project_ref, workspace_ref, default_project=False)
    needle = parsed.text.replace("-", "").lower()
    files = _list_all_files(ctx, ws_id, proj_id)
    return artifacts.FileId(_pick_prefix(files, lambda f: f.file_id, needle, "file", raw))


def _checked_ver(ctx: CliContext, uid: UUID, proj_ref: str | None, ws_ref: str | None) -> FileVersionId:
    vview = cast("artifacts.GetFileVersionView", ctx.client.ask(artifacts.GetFileVersion(uid)))
    if proj_ref is not None or ws_ref is not None:
        _checked_file(ctx, artifacts.FileId(vview.file_id), project_ref=proj_ref, workspace_ref=ws_ref)
    return FileVersionId(uid)


def resolve_file_version_id(
    ctx: CliContext,
    raw: str,
    *,
    version_no: int | None = None,
    project_ref: str | None = None,
    workspace_ref: str | None = None,
) -> FileVersionId:
    """Resolve ``fv:<uuid>``, ``file:<uuid>``, bare UUID or prefix (optionally ``--version N``)."""
    if version_no is not None:
        fid = resolve_file_id(ctx, raw, project_ref=project_ref, workspace_ref=workspace_ref)
        _checked_file(ctx, fid, project_ref=project_ref, workspace_ref=workspace_ref)
        for ver in _list_all_versions(ctx, fid):
            if ver.version_no == version_no:
                return FileVersionId(ver.file_version_id)
        raise NotFound(ErrorCode.NOT_FOUND, f"version v{version_no} not found on file {fid}")
    if raw.startswith("fv:"):
        uid = parse_ref(RefKind.FILE_VERSION, raw).uuid
        assert uid is not None  # noqa: S101
        return _checked_ver(ctx, uid, project_ref, workspace_ref)
    if raw.startswith("file:"):
        fid = resolve_file_id(ctx, raw, project_ref=project_ref, workspace_ref=workspace_ref)
        fview = _checked_file(ctx, fid, project_ref=project_ref, workspace_ref=workspace_ref)
        return FileVersionId(fview.current_version.file_version_id)
    direct = as_uuid(raw)
    if direct is not None:
        try:
            return _checked_ver(ctx, direct, project_ref, workspace_ref)
        except NotFound:
            fview = _checked_file(
                ctx, artifacts.FileId(direct), project_ref=project_ref, workspace_ref=workspace_ref
            )
            return FileVersionId(fview.current_version.file_version_id)
    needle = parse_ref(RefKind.FILE_VERSION, raw).text.replace("-", "").lower()
    ws_id, proj_id = _resolve_scope(ctx, project_ref, workspace_ref, default_project=False)
    files = _list_all_files(ctx, ws_id, proj_id)
    if any(f.file_id.hex.lower().startswith(needle) for f in files):
        fid = artifacts.FileId(_pick_prefix(files, lambda f: f.file_id, needle, "file", raw))
        fview = _checked_file(ctx, fid, project_ref=project_ref, workspace_ref=workspace_ref)
        return FileVersionId(fview.current_version.file_version_id)
    versions = [v for s in files for v in _list_all_versions(ctx, artifacts.FileId(s.file_id))]
    return FileVersionId(_pick_prefix(versions, lambda v: v.file_version_id, needle, "version", raw))


def _render_upload(ctx: CliContext, out: dict[str, Any], cmd_name: str, key: str) -> int:
    return render(
        ctx,
        out,
        human=lambda d: f"file {d['file_id']} v{d['version_no']} ({d['digest']}, {d['size_bytes']} B)",
        command=cmd_name,
        essential=lambda d: str(d[key]),
    )


def _compact(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if v is not None}


def _upload_dispatch(
    ctx: CliContext, ws: WorkspaceId, args: argparse.Namespace, path: str, base: dict[str, Any], *, new: bool
) -> int:
    idem, key = ctx.new_idempotency_key(), "file_id" if new else "file_version_id"
    h_req = {**base, "path": path, "workspace_id": str(ws), "idempotency_key": idem}
    if new:
        h_req["title"] = args.title
    via_host = _try_host_upload(ctx, cast("JsonObject", h_req))
    if via_host is not None:
        return _render_upload(ctx, dict(via_host), args.command_name, key)
    orig, s, blob = _stage_local(ctx, ws, path, args.media_type)
    dto = {**base, "blob": blob, "original_filename": orig, "source": {"kind": "upload"}}
    if new:
        dto["title"] = args.title or orig
        if dto.get("classification") is None:
            dto.pop("classification", None)
    cmd: object = artifacts.AddFile.from_json(dto) if new else artifacts.AddFileVersion.from_json(dto)
    added: Any = ctx.client.dispatch(cmd, idempotency_key=idem)
    out = {**added.to_json(), "digest": s.digest, "size_bytes": s.size, "original_filename": orig}
    return _render_upload(ctx, out, args.command_name, key)


def _add(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id, proj_id = _resolve_scope(ctx, args.project, args.workspace, default_project=True)
    base: dict[str, Any] = {
        "workspace_id": str(ws_id),
        "project_id": str(proj_id) if proj_id is not None else None,
        "origin": "upload",
        "classification": args.classification,
        "declared_media_type": args.media_type,
        "description": args.description,
        "acknowledge": [str(x) for x in (args.ack or ())],
    }
    return _upload_dispatch(ctx, ws_id, args, args.path, base, new=True)


def _version(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.first == "add" and args.third is not None:
        file_ref, local_path = str(args.second), str(args.third)
    elif args.third is None:
        file_ref, local_path = str(args.first), str(args.second)
    else:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "expected `skm file version [add] FILE PATH`")
    fid = resolve_file_id(ctx, file_ref, project_ref=args.project, workspace_ref=args.workspace)
    existing = _checked_file(ctx, fid, project_ref=args.project, workspace_ref=args.workspace)
    exp_ver = args.expected_version if args.expected_version is not None else existing.row_version
    base = {
        "file_id": str(fid),
        "expected_row_version": exp_ver,
        "declared_media_type": args.media_type,
        "description": args.description,
        "acknowledge": [str(x) for x in (args.ack or ())],
    }
    return _upload_dispatch(ctx, WorkspaceId(existing.workspace_id), args, local_path, base, new=False)


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id, proj_id = _resolve_scope(ctx, args.project, args.workspace, default_project=False)
    state_f = None if args.state == "all" else args.state
    proj_s = str(proj_id) if proj_id is not None else None

    def _step(cur: str | None) -> tuple[Sequence[artifacts.FileSummaryView], str | None]:
        raw_q = {"workspace_id": str(ws_id), "project_id": proj_s, "state": state_f, "origin": args.origin}
        q_doc = _compact({**raw_q, "after": cur, "limit": args.limit})
        v = cast("artifacts.ListFilesView", ctx.client.ask(artifacts.ListFiles.from_json(q_doc)))
        return v.items, v.next

    col = Column[artifacts.FileSummaryView]
    cols = (
        col("id", lambda f: f.file_id),
        col("title", lambda f: f.title),
        col("classification", lambda f: f.classification),
        col("origin", lambda f: f.origin),
        col("state", lambda f: f.state),
        col("row_version", lambda f: f.row_version),
    )
    page = _paginate(_step, after=args.after, fetch_all=args.fetch_all)
    return render_page(ctx, page, columns=cols, command=args.command_name)


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    fid = resolve_file_id(ctx, args.file_ref, project_ref=args.project, workspace_ref=args.workspace)
    view = _checked_file(ctx, fid, project_ref=args.project, workspace_ref=args.workspace)
    vers = [v.to_json() for v in _list_all_versions(ctx, fid)]
    payload: dict[str, Any] = {**view.to_json(), "versions": vers}

    def _human(doc: Mapping[str, Any]) -> list[str]:
        cur = cast("Mapping[str, Any]", doc["current_version"])
        top = [(k, doc[k]) for k in ("file_id", "title", "workspace_id")]
        mid = [(k, doc[k]) for k in ("classification", "origin", "state", "row_version")]
        tail = [
            ("current_version", f"v{cur['version_no']} ({cur['file_version_id']})"),
            ("filename", cur["original_filename"]),
            ("size_bytes", cur["size_bytes"]),
            ("digest", cur["digest"]),
        ]
        lines = kv_lines(ctx, [*top, ("project_id", doc["project_id"] or "-"), *mid, *tail])
        rows = [
            [v["version_no"], v["file_version_id"], v["original_filename"], v["size_bytes"], v["digest"]]
            for v in cast("Sequence[Mapping[str, Any]]", doc["versions"])
        ]
        if rows:
            lines.extend(render_table(ctx, ("no", "version_id", "filename", "size", "digest"), rows))
        return lines

    return render(
        ctx, payload, human=_human, command=args.command_name, essential=lambda d: str(d["file_id"])
    )


def _versions(args: argparse.Namespace, ctx: CliContext) -> int:
    fid = resolve_file_id(ctx, args.file_ref, project_ref=args.project, workspace_ref=args.workspace)
    _checked_file(ctx, fid, project_ref=args.project, workspace_ref=args.workspace)

    def _step(cur: str | None) -> tuple[Sequence[artifacts.FileVersionView], str | None]:
        q = artifacts.ListFileVersions(fid, cur, args.limit)
        v = cast("artifacts.ListFileVersionsView", ctx.client.ask(q))
        return v.items, v.next

    col = Column[artifacts.FileVersionView]
    cols = (
        col("no", lambda v: v.version_no),
        col("version_id", lambda v: v.file_version_id),
        col("filename", lambda v: v.original_filename),
        col("size", lambda v: v.size_bytes),
        col("digest", lambda v: v.digest),
        col("by", lambda v: v.created_by),
        col("at", lambda v: v.created_at.isoformat()),
    )
    page = _paginate(_step, after=args.after, fetch_all=args.fetch_all)
    return render_page(ctx, page, columns=cols, command=args.command_name)


def _read_version_bytes(ctx: CliContext, ver_id: FileVersionId) -> bytes:
    with ctx.client.open_file_version_content(ver_id) as stream:
        return b"".join(iter(lambda: stream.read(_CHUNK_BYTES), b""))


def _cat(args: argparse.Namespace, ctx: CliContext) -> int:
    ver_id = resolve_file_version_id(
        ctx, args.target, version_no=args.version_no, project_ref=args.project, workspace_ref=args.workspace
    )
    if args.output is not None:
        raw, out_p = _read_version_bytes(ctx, ver_id), Path(args.output)
        atomic_write(out_p, raw, mode=0o600)
        res: dict[str, Any] = {"file_version_id": str(ver_id), "output": str(out_p), "size_bytes": len(raw)}
        return render(
            ctx,
            res,
            human=lambda d: f"wrote {d['size_bytes']} B to {d['output']}",
            command=args.command_name,
            essential=lambda d: str(d["output"]),
        )
    if ctx.json:
        raw = _read_version_bytes(ctx, ver_id)
        try:
            text: str | None = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        b64 = base64.b64encode(raw).decode("ascii")
        doc = {"file_version_id": str(ver_id), "size_bytes": len(raw), "text": text, "content_b64": b64}
        return render(ctx, doc, human=lambda d: str(d["size_bytes"]), command=args.command_name)
    binary_out = getattr(ctx.stdout, "buffer", None)
    with ctx.client.open_file_version_content(ver_id) as stream:
        while piece := stream.read(_CHUNK_BYTES):
            if binary_out is not None:
                binary_out.write(piece)
            else:
                ctx.stdout.write(piece.decode("utf-8", errors="surrogateescape"))
    (binary_out if binary_out is not None else ctx.stdout).flush()
    return 0


def _mutate_state(args: argparse.Namespace, ctx: CliContext, *, trash: bool) -> int:
    fid = resolve_file_id(ctx, args.file_ref, project_ref=args.project, workspace_ref=args.workspace)
    existing = _checked_file(ctx, fid, project_ref=args.project, workspace_ref=args.workspace)
    exp = args.expected_version if args.expected_version is not None else existing.row_version
    if trash and not (args.yes or ctx.confirm(f"Trash file {fid}?")):
        msg = "confirmation required; pass --yes"
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, msg, details={"reason": "confirmation_required"})
    cmd: object = (
        artifacts.TrashFile(file_id=fid, expected_row_version=exp, reason=args.reason)
        if trash
        else artifacts.RestoreFile(file_id=fid, expected_row_version=exp)
    )
    res = cast(
        "artifacts.TrashFileResult | artifacts.RestoreFileResult",
        ctx.client.dispatch(cmd, idempotency_key=ctx.new_idempotency_key()),
    )
    label = "trashed" if trash else "restored"
    return render(
        ctx,
        res,
        human=lambda r: f"{label} {r.file_id} (v{r.row_version})",
        command=args.command_name,
        essential=lambda r: str(r.file_id),
    )


def _trash(args: argparse.Namespace, ctx: CliContext) -> int:
    return _mutate_state(args, ctx, trash=True)


def _restore(args: argparse.Namespace, ctx: CliContext) -> int:
    return _mutate_state(args, ctx, trash=False)


_DISPATCH: Final = {
    "add": ("artifacts.add_file", _add),
    "version": ("artifacts.add_file_version", _version),
    "list": ("artifacts.list_files", _list),
    "show": ("artifacts.get_file", _show),
    "versions": ("artifacts.list_file_versions", _versions),
    "cat": ("artifacts.open_file_version_content", _cat),
    "trash": ("artifacts.trash_file", _trash),
    "restore": ("artifacts.restore_file", _restore),
}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("file", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", metavar="VERB", required=True)
    for verb in ("add", "version", "list", "show", "versions", "cat", "trash", "restore"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(command_name=_DISPATCH[verb][0], run=_DISPATCH[verb][1])
        if verb == "add":
            command.add_argument("path", help="local file path to upload")
            command.add_argument("--title", help="file title (default: filename)")
            command.add_argument(
                "--classification",
                choices=("public", "internal", "confidential", "restricted"),
                help="classification",
            )
        elif verb == "version":
            command.add_argument("first", help="file reference or 'add'")
            command.add_argument("second", help="local file path or file reference")
            command.add_argument("third", nargs="?", help="local file path when 'add' is used")
        elif verb == "list":
            command.add_argument(
                "--state", choices=("active", "trashed", "all"), default="active", help="lifecycle state"
            )
            command.add_argument(
                "--origin",
                choices=("upload", "evidence", "transcript", "patch", "report", "import", "capture"),
                help="origin",
            )
        elif verb == "cat":
            command.add_argument("target", help="file or file version reference")
            command.add_argument("--version", dest="version_no", type=int, help="version number")
            command.add_argument("--output", help="write bytes to PATH instead of stdout")
        if verb in ("show", "versions", "trash", "restore"):
            command.add_argument("file_ref", help="file reference")
        if verb in ("add", "version"):
            command.add_argument("--media-type", help="declared media type")
            command.add_argument("--description", default="", help="version description")
            command.add_argument("--ack", action="append", help="acknowledge safety rule")
        if verb in ("version", "trash", "restore"):
            command.add_argument("--expected-version", type=int, help="expected file row_version")
        if verb == "trash":
            command.add_argument("--reason", default="cli trash", help="reason for trashing")
            command.add_argument("--yes", action="store_true", help="skip confirmation")
        if verb in ("list", "versions"):
            command.add_argument("--after", help="pagination cursor")
            command.add_argument("--limit", type=int, default=50, help="page size")
            command.add_argument("--all", dest="fetch_all", action="store_true", help="fetch all pages")
        command.add_argument("--project", help="project reference")
        command.add_argument("--workspace", help="workspace reference")


GROUP: Final = CommandGroup(
    name="file",
    help="upload, inspect, cat, trash and restore artifacts",
    register=register,
    requires_backend=True,
    module="artifacts",
    order=55,
)
