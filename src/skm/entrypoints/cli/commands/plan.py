"""``skm plan`` (cli §6.6, planning §14): create, inspect, edit, validate, rebase and publish plans."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast
from uuid import UUID

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli import output as _o
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id, resolve_project_view
from skm.entrypoints.cli.commands.research import query_spec, run_host_research
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.editor import resolve_editor
from skm.entrypoints.cli.refs import RefForm, RefKind, as_uuid, parse_ref
from skm.kernel.error_codes import ErrorCategory, ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound, SkmError, ValidationFailed, error_for
from skm.kernel.ids import PlanId, RevisionId, WorkspaceId
from skm.kernel.outcomes import Diagnostic, Severity
from skm.kernel.pagination import Page
from skm.modules.planning.public import DraftId
from skm.platform.fs.atomic_write import atomic_write

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = ["GROUP", "register", "resolve_plan_id", "resolve_revision_id"]

_HELP: Final = {
    "design": "record a plan design brief from JSON",
    "approve": "sign a revision readiness report and issue a visa",
    "create": "create a plan in the active project and open an initial draft",
    "list": "list plans in the active project",
    "show": "show plan details, current revision tree or a single entity",
    "entities": "list specification entity outlines for a revision or draft",
    "text": "read a UTF-8 text fragment by JSON pointer from a plan or entity",
    "revisions": "list published revisions of a plan",
    "diff": "compare two revisions or a draft against its base revision",
    "preview": "preview ready execution lanes, conflicts and waiting tasks",
    "simulate": "estimate plan tokens, cost and model processing time",
    "research": "collect design research and print its provenance",
    "stats": "compute structural, coverage and graph statistics for a plan",
    "archive": "archive a plan and abandon its open drafts",
    "restore": "publish a new revision restored from a previous revision number",
    "publish": "publish an open draft as a new immutable plan revision",
    "export": "export a portable specification document and metadata",
    "import": "import a portable specification into a new plan or draft",
    "draft": "open, inspect, edit, save, validate, preview, rebase or abandon drafts",
}


class _CliFinding(NamedTuple):
    code: str
    severity: str
    entity: str | None
    message: str


def _present(**members: Any) -> JsonObject:
    return {k: v for k, v in members.items() if v is not None}


def _bad(msg: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, msg, details=details)


def _ask(ctx: CliContext, name: str, payload: Mapping[str, Any], *, w: bool = False) -> Any:
    mod, attr = name.split(".")[0], "commands" if w else "queries"
    specs = (s for m in MANIFESTS if m.id == mod for s in getattr(m, attr))
    try:
        dto = next(s for s in specs if s.name == name).dto.from_json(cast("JsonObject", dict(payload)))
    except (ValueError, TypeError) as err:
        raise _bad(str(err)) from err
    return ctx.client.dispatch(dto, idempotency_key=ctx.new_idempotency_key()) if w else ctx.client.ask(dto)


def _dispatch(ctx: CliContext, name: str, payload: Mapping[str, Any]) -> Any:
    return _ask(ctx, name, payload, w=True)


def _out(c: CliContext, cmd: str, val: Any, ln: Sequence[str], ess: str, dg: Any = ()) -> int:
    return _o.render(c, val, human=lambda _: list(ln), command=cmd, diagnostics=dg, essential=lambda _: ess)


def _kv(ctx: CliContext, o: Any, flds: str) -> list[str]:
    return _o.kv_lines(ctx, [(f, getattr(o, f) if getattr(o, f) is not None else "-") for f in flds.split()])


def _page(ctx: CliContext, cmd: str, items: list[Any], nxt: Any, cols: str) -> int:
    parts = [x.partition(":") for x in cols.split()]
    c = tuple(_o.Column[Any](h, lambda i, a=attr: getattr(i, a) or "-") for h, _, attr in parts)
    return _o.render_page(ctx, Page[Any](items=tuple(items), next=nxt), columns=c, command=cmd)


def _out_findings(ctx: CliContext, cmd: str, val: Any, msg: str, ess: str, findings: Sequence[Any]) -> int:
    sm = {"error": Severity.ERROR, "warning": Severity.WARNING, "info": Severity.INFO}
    diags, rows = cast("list[Diagnostic]", []), cast("list[_CliFinding]", [])
    for f in findings:
        s, t = str(getattr(f.severity, "value", f.severity)), getattr(f, "entity_key", None) or f.pointer
        dc = str(f.code).replace(".", "_").replace("-", "_").upper()
        diags.append(Diagnostic(code=dc, severity=sm.get(s, Severity.INFO), message=str(f.message), target=t))
        rows.append(_CliFinding(str(f.code), s, t, str(f.message)))
    code = _out(ctx, cmd, val, [msg], ess, diags)
    return (_o.render_findings(ctx, rows) or code) if not ctx.quiet else code


def resolve_plan_id(ctx: CliContext, raw: str, *, project_ref: str | None = None) -> PlanId:
    ref = parse_ref(RefKind.PLAN, raw)
    try:
        q = {"project_id": str(resolve_project_id(ctx, project_ref)), "ref": raw}
        return PlanId(UUID(str(_ask(ctx, "planning.resolve_plan_ref", q).plan_id)))
    except Exception:
        if ref.form is RefForm.UUID and ref.uuid is not None and project_ref is None:
            return PlanId(ref.uuid)
        raise


def resolve_revision_id(ctx: CliContext, pid: PlanId, raw: str | None) -> RevisionId:
    ref = parse_ref(RefKind.REVISION, None if raw == "current" else raw)
    if ref.form is RefForm.UUID and ref.uuid is not None:
        return RevisionId(ref.uuid)
    if ref.form not in (RefForm.NUMBER, RefForm.CURRENT):
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, f"invalid revision {raw!r}", details={})
    q = {"plan_id": str(pid), **({"revision_no": ref.number} if ref.number else {"current": True})}
    return RevisionId(UUID(str(_ask(ctx, "planning.get_revision", q).revision_id)))


def _resolve_draft_pair(ctx: CliContext, pid: PlanId, raw: str | None, exp_v: int | None = None):
    cl = None if raw in (None, "open", "current") else (f"draft:{raw}" if as_uuid(raw) else raw)
    ref = parse_ref(RefKind.DRAFT, cl) if cl is not None else None
    if ref is not None and ref.form is RefForm.UUID and ref.uuid is not None:
        q = {"plan_id": str(pid), "draft_id": str(ref.uuid)}
        v = exp_v if exp_v is not None else int(_ask(ctx, "planning.get_draft", q).edit_version)
        return DraftId(ref.uuid), v
    items = list(_ask(ctx, "planning.list_drafts", {"plan_id": str(pid)}).items)
    m = items if ref is None else [d for d in items if str(d.draft_id).lower().startswith(ref.text.lower())]
    if not m:
        raise NotFound(ErrorCode.NOT_FOUND, "draft not found", details={"plan_id": str(pid)})
    if len(m) > 1:
        raise ValidationFailed(ErrorCode.AMBIGUOUS_REFERENCE, "multiple open drafts", details={})
    return DraftId(UUID(str(m[0].draft_id))), (exp_v if exp_v is not None else int(m[0].edit_version))


def _source_payload(ctx: CliContext, plan_id: PlanId, a: argparse.Namespace) -> JsonObject:
    rev_r, dr_r = getattr(a, "revision", None), getattr(a, "draft", None)
    if rev_r is not None and dr_r is not None:
        raise _bad("pass either --revision or --draft, not both", reason="conflicting_source")
    if dr_r is None:
        return {"plan_id": str(plan_id), "revision_id": str(resolve_revision_id(ctx, plan_id, rev_r))}
    did, ver = _resolve_draft_pair(ctx, plan_id, dr_r, getattr(a, "expected_version", None))
    return {"plan_id": str(plan_id), "draft_id": str(did), "expected_edit_version": ver}


def _parse_kv(entries: Sequence[str] | None, flag: str) -> list[tuple[str, str]]:
    for e in entries or ():
        if "=" not in e:
            raise _bad(f"expected KEY=VALUE for {flag}, got {e!r}", flag=e)
    return [(e.partition("=")[0].strip(), e.partition("=")[2].strip()) for e in (entries or ())]


def _paginate(ctx: CliContext, name: str, base: Mapping[str, Any], ck: str, cv: Any, lim: int, all_p: bool):
    items: list[Any] = []
    cur, last = cv, cast("Any", None)
    while True:
        last = _ask(ctx, name, {**base, "limit": lim, **_present(**{ck: cur})})
        items.extend(last.items)
        nxt = getattr(last, "next", getattr(last, "next_cursor", None))
        if not all_p or nxt is None:
            return items, (None if all_p else nxt), last
        cur = int(nxt) if ck == "before" else str(nxt)


def _load_json(path_str: str) -> JsonValue:
    try:
        raw = sys.stdin.read() if path_str == "-" else Path(path_str).read_text(encoding="utf-8")
        return cast("JsonValue", json.loads(raw))
    except (OSError, ValueError) as err:
        raise _bad(f"cannot read valid JSON from {path_str!r}: {err}", path=path_str) from err


def _run_top(a: argparse.Namespace, ctx: CliContext) -> int:  # noqa: PLR0911, PLR0912, PLR0915
    verb, cmd = a.plan_verb, a.command_name
    if verb in {"design", "approve"}:
        plan_id = str(resolve_plan_id(ctx, a.plan, project_ref=a.project))
        if verb == "approve":
            out = _dispatch(
                ctx, cmd, {"plan_id": plan_id, "readiness_report_id": a.report, "reason": a.reason}
            )
            return _out(ctx, cmd, out, [f"Signed revision visa {out.visa_id}"], str(out.visa_id))
        brief = _load_json(a.file)
        if not isinstance(brief, dict) or "plan_id" in brief:
            raise _bad("design brief file must be a JSON object without plan_id", path=a.file)
        out = _dispatch(ctx, cmd, {**brief, "plan_id": plan_id})
        return _out(ctx, cmd, out, [f"Recorded design brief {out.design_brief_id}"], str(out.design_brief_id))
    if verb == "create":
        pid, inp = str(resolve_project_id(ctx, a.project)), cast("dict[str, JsonValue]", {})
        for k, v in _parse_kv(a.inputs, "--input"):
            if not k or k in inp:
                raise _bad("template input keys must be nonempty and unique", field=k)
            low, is_i = v.lower(), v.removeprefix("-").isdigit() and v.isascii()
            inp[k] = low == "true" if low in ("true", "false") else (int(v) if is_i else v)
        if (inp and a.template is None) or (a.no_draft and a.template is not None):
            raise _bad("--input requires --template and --no-draft forbids --template")
        q = _present(project_id=pid, title=a.title, template_key=a.template, template_inputs=inp or None)
        out = cast("dict[str, Any]", _dispatch(ctx, cmd, q).to_json())
        if not a.no_draft and out.get("draft_id") is None:
            op = _dispatch(ctx, "planning.open_draft", {"plan_id": str(out["plan_id"]), "base": "empty"})
            out.update(draft_id=str(op.draft_id), edit_version=int(op.edit_version))
        ln = [f"created plan {out['alias']} ({out['plan_id']})"]
        ln.extend([f"draft: {out['draft_id']} (v{out['edit_version']})"] if out.get("draft_id") else [])
        return _out(ctx, cmd, out, ln, str(out["plan_id"]))
    if verb == "list":
        q = {"project_id": str(resolve_project_id(ctx, a.project)), "state": a.state}
        items, nxt, _ = _paginate(ctx, cmd, q, "after", a.after, a.limit, a.all)
        return _page(ctx, cmd, items, nxt, "alias:alias title:title state:lifecycle_state plan_id:plan_id")
    if verb == "import":
        as_new, as_dr = a.new_plan or a.as_mode == "new-plan", a.new_draft or a.as_mode == "new-draft"
        ld = _load_json(a.file)
        if (as_new and as_dr) or (a.keep_ids and a.remap_ids) or not isinstance(ld, Mapping):
            raise _bad("invalid import flags or JSON object", path=a.file)
        wrap = isinstance(ld.get("document"), Mapping)
        doc = dict(cast("Mapping[str, JsonValue]", ld["document"] if wrap else ld))
        if (raw_m := ld.get("export_meta") if wrap else None) is not None and not isinstance(raw_m, Mapping):
            raise _bad("export_meta must be a JSON object", path=a.file)
        meta = dict(cast("Mapping[str, JsonValue]", raw_m)) if isinstance(raw_m, Mapping) else None
        mode = "new_draft" if not as_new and (as_dr or a.plan) else "new_plan"
        pid, same_plan = str(resolve_project_id(ctx, a.project)), False
        p = {**_present(project_id=pid, document=doc, mode=mode, title=a.title), "keep_ids": not a.remap_ids}
        s_raw = meta.get("source") if meta else None
        sm = cast("Mapping[str, Any]", s_raw) if isinstance(s_raw, Mapping) else None
        if mode == "new_draft":
            if a.plan is None:
                raise _bad("--plan is required when importing as new-draft", field="plan_id")
            p["plan_id"] = str(pl_id := resolve_plan_id(ctx, a.plan, project_ref=a.project))
            same_plan = sm is not None and sm.get("plan_id") == p["plan_id"]
            mk = sm.get("kind") if same_plan and sm is not None else None
            m_b = (sm.get("revision_id") if mk == "revision" else sm.get("base_revision_id")) if sm else None
            has_mb = bool(m_b) if mk == "revision" else (mk == "draft" and "base_revision_id" in (sm or ()))
            arg_b = None if a.base in (None, "empty") else str(resolve_revision_id(ctx, pl_id, a.base))
            if (a.base is None and not has_mb) or (a.base and has_mb and arg_b != (m_b and str(m_b))):
                raise _bad("missing or conflicting new-draft base provenance", field="base")
            p["source_base_revision_id"] = arg_b if a.base is not None else (m_b and str(m_b))
        if meta is not None and (mode == "new_plan" or same_plan):
            p["export_meta"] = meta
        rb_map = dict(_parse_kv(a.rebinds, "--rebind"))
        if a.materials is not None:
            if not (mdir := Path(a.materials)).is_dir():
                raise _bad(f"materials directory not found: {a.materials!r}", path=a.materials)
            files = [fp for fp in sorted(mdir.rglob("*")) if fp.is_file()]
            by_dig = {f"sha256:{hashlib.sha256(b := f.read_bytes()).hexdigest()}": (f.name, b) for f in files}
            ws_id = WorkspaceId(resolve_project_view(ctx, a.project).workspace_id)
            m_raw = meta.get("materials") if meta else None
            mats = cast("list[Any]", m_raw) if isinstance(m_raw, list) else []
            for m in (cast("Mapping[str, Any]", x) for x in mats if isinstance(x, Mapping)):
                mk, dg = m.get("material_key"), m.get("content_digest")
                if isinstance(mk, str) and mk not in rb_map and isinstance(dg, str) and dg in by_dig:
                    fn, b = by_dig[dg]
                    ofn, mt = str(m.get("original_filename") or fn), str(m.get("media_type") or "text/plain")
                    blob = ctx.client.upload_blob(ws_id, [b], size=len(b), expected_digest=dg, media_type=mt)
                    af = _present(workspace_id=str(ws_id), project_id=pid, title=ofn, blob=blob.to_json())
                    af.update(origin="upload", original_filename=ofn, source={"kind": "upload"})
                    rb_map[mk] = str(_dispatch(ctx, "artifacts.add_file", af).file_version_id)
        rbs = [{"material_key": k, "file_version_id": v} for k, v in rb_map.items()]
        res = _dispatch(ctx, cmd, {**p, **_present(material_rebind=rbs or None)})
        m = f"imported into {res.alias} ({res.plan_id}) draft {res.draft_id}"
        return _out(ctx, cmd, res, [m], str(res.draft_id))

    plan_id = resolve_plan_id(ctx, a.plan, project_ref=a.project)
    pid_s = str(plan_id)
    if verb == "show":
        if a.format == "json" and isinstance(ctx, CliSession) and not ctx.json:
            ctx.options = replace(ctx.options, json=True)
        if a.entity is not None:
            ev = _ask(ctx, "planning.get_entity", {**_source_payload(ctx, plan_id, a), "ref": a.entity})
            k = _kv(ctx, ev, "display_key entity_kind entity_id")
            return _out(ctx, "planning.get_entity", ev, k, str(ev.entity_id))
        pv = _ask(ctx, cmd, {"plan_id": pid_s})
        if not (a.tree or a.revision is not None):
            flds = "plan_id alias title lifecycle_state current_revision_no open_drafts"
            return _out(ctx, cmd, pv, _kv(ctx, pv, flds), str(pv.plan_id))
        r_id, tb = str(resolve_revision_id(ctx, plan_id, a.revision)), bool(a.tree)
        rq = {"plan_id": pid_s, "revision_id": r_id, "include_tree": tb, "include_document": not tb}
        rv, tl, depth = _ask(ctx, "planning.get_revision", rq), cast("list[str]", []), 3
        if rv.tree:
            with contextlib.suppress(Exception):
                sq = {"key": "planning.display.tree_depth", "scope": {"level": "plan", "scope_id": pid_s}}
                depth = v_d if 1 <= (v_d := int(_ask(ctx, "settings.get_value", sq).value)) <= 3 else 3
            for ph in rv.tree.get("phases", ()):
                tl.append(f"{ph['key']}  {ph['title']} [{ph['design_state']}]")
                for it in ph.get("items", ()) if depth >= 2 else ():
                    tl.append(f"  {it['key']}  {it['title']} ({it['work_kind']})")
                    u_seq = it.get("units", ()) if depth >= 3 else ()
                    tl.extend(f"    {u['key']}  {u['title']}" for u in u_seq)
            tl = tl or ["(empty tree)"]
        tl = [f"{pv.alias} r{rv.revision_no}", *tl]
        return _out(ctx, "planning.get_revision", rv, tl, str(rv.revision_id))
    if verb == "entities":
        kinds = list(dict.fromkeys(a.kinds)) if a.kinds else None
        q = {**_source_payload(ctx, plan_id, a), **_present(kinds=kinds)}
        items, nxt, last = _paginate(ctx, cmd, q, "after", a.after, a.limit, a.all)
        if nxt is not None and not ctx.json:
            ctx.stderr.write("more results are available (use --all)\n")
        r = [[i.display_key, str(i.entity_kind), i.title, i.children_count, i.entity_id] for i in items]
        doc: JsonObject = {"source": _o.to_jsonable(last.source), "items": [_o.to_jsonable(i) for i in items]}
        doc["next_cursor"] = nxt
        cols = ("key", "kind", "title", "children", "entity_id")
        tbl = _o.render_table(ctx, cols, r) if r else ["no entities"]
        return _out(ctx, cmd, doc, tbl, "\n".join(str(i.display_key) for i in items))
    if verb == "text":
        q = {**_source_payload(ctx, plan_id, a), "target": a.target, "pointer": a.pointer}
        v = _ask(ctx, cmd, {**q, "offset_bytes": a.offset_bytes, "max_bytes": a.max_bytes})
        ln = [v.text, *([f"(truncated: {v.omitted_bytes}B omitted)"] if v.truncated else [])]
        return _out(ctx, cmd, v, ln, str(v.text))
    if verb == "revisions":
        items, nxt, _ = _paginate(ctx, cmd, {"plan_id": pid_s}, "before", a.before, a.limit, a.all)
        c = "rev:revision_no origin:origin digest:content_digest reason:change_reason"
        return _page(ctx, cmd, items, nxt, c)
    if verb == "diff":
        p: JsonObject = {"plan_id": pid_s}
        if a.draft is not None or a.b == "draft":
            did, ver = _resolve_draft_pair(ctx, plan_id, a.draft, a.expected_version)
            f_rev = str(resolve_revision_id(ctx, plan_id, a.a)) if a.a not in (None, "draft") else None
            p.update(draft_id=str(did), expected_edit_version=ver, **_present(from_revision_id=f_rev))
        else:
            ra = str(resolve_revision_id(ctx, plan_id, a.a))
            p["to_revision_id"] = str(resolve_revision_id(ctx, plan_id, a.b)) if a.a else ra
            p.update(_present(from_revision_id=ra if a.a else None))
        v = _ask(ctx, cmd, p)
        r = [[e.change, e.entity_kind, e.key_after or e.key_before or "-", e.entity_id] for e in v.entities]
        s = v.summary
        hdr = f"diff {v.from_digest} -> {v.to_digest} (+{s['added']} -{s['removed']} ~{s['changed']})"
        tbl = _o.render_table(ctx, ("change", "kind", "key", "entity_id"), r) if r else []
        return _out(ctx, cmd, v, [hdr, *tbl], f"{v.from_digest}..{v.to_digest}")
    if verb == "simulate":
        query = {**_source_payload(ctx, plan_id, a), **_present(tokens_per_second=a.tokens_per_second)}
        result = _ask(ctx, cmd, query)

        def interval(value: Any) -> str:
            return "unknown" if value is None else f"{value.min} to {value.max}"

        lines = [
            f"Basis: {result.basis} ({result.task_count} work tasks)",
            f"Tokens: {interval(result.tokens)}",
            f"Cost (USD micros): {interval(result.cost_usd_micros)}",
            f"Model processing time (s): {interval(result.duration_seconds)}",
        ]
        return _out(ctx, cmd, result, lines, "\n".join(lines))
    if verb == "preview":
        q = {**_source_payload(ctx, plan_id, a), "limit": a.limit}
        v = _ask(ctx, cmd, {**q, **_present(assume_done=a.assume_done, assume_granted=a.assume_granted)})
        ln = [f"ready lanes: {len(v.lanes)}, conflicts: {len(v.conflicts)}, waiting: {len(v.waiting)}"]
        ln.extend(f"lane {idx + 1}: {', '.join(x.tasks)}" for idx, x in enumerate(v.lanes))
        return _out(ctx, cmd, v, ln, "\n".join(",".join(x.tasks) for x in v.lanes))
    if verb == "stats":
        v = _ask(ctx, cmd, _source_payload(ctx, plan_id, a))
        ln = _o.kv_lines(ctx, [(f, v.counts.get(f, "-")) for f in ("phases", "items", "units")])
        return _out(ctx, cmd, v, ln + _kv(ctx, v.graph, "tasks edges"), f"items={v.counts['items']}")
    if verb == "archive":
        if not (getattr(a, "yes", False) or ctx.assume_yes or ctx.confirm(f"Archive plan {plan_id}?")):
            raise _bad("Confirmation required; pass --yes to confirm", reason="confirmation_required")
        v = _dispatch(ctx, cmd, _present(plan_id=pid_s, expected_row_version=a.expected_version))
        return _out(ctx, cmd, v, [f"archived plan {v.plan_id} (row_version {v.row_version})"], str(v.plan_id))
    if verb == "restore":
        if (raw_rev := a.revision_opt if a.revision_opt is not None else a.rev) is None:
            raise _bad("pass a revision number (REV or --revision N)", field="revision_no")
        rq = {"plan_id": pid_s, "revision_id": str(resolve_revision_id(ctx, plan_id, str(raw_rev)))}
        r_no = parse_ref(RefKind.REVISION, str(raw_rev)).number
        rev_no = r_no or int(_ask(ctx, "planning.get_revision", rq).revision_no)
        cur = _ask(ctx, "planning.get_plan", {"plan_id": pid_s}).current_revision_id
        exp = str(resolve_revision_id(ctx, plan_id, ec)) if (ec := a.expected_current) else (cur and str(cur))
        q = _present(plan_id=pid_s, revision_no=rev_no, reason=a.reason, expected_current_revision_id=exp)
        v, m = _dispatch(ctx, cmd, q), "restored r{0.restored_from_revision_no} as r{0.revision_no}"
        return _out(ctx, cmd, v, [m.format(v)], str(v.revision_id))
    if verb == "publish":
        did, ver = _resolve_draft_pair(ctx, plan_id, a.draft, a.expected_version)
        if (dig := a.expected_content_digest) is None:
            pq = {"plan_id": pid_s, "draft_id": str(did), "expected_edit_version": ver}
            pr = _ask(ctx, "planning.preview_publication", pq)
            dig, ver = str(pr.content_digest), int(pr.source.edit_version)
            if not ctx.json and not ctx.quiet:
                a_n, r_n = pr.diff.summary["added"], pr.diff.summary["removed"]
                ctx.stderr.write(_o.safe_text(ctx, f"preview: digest {dig} (+{a_n} -{r_n})\n"))
        q = {"plan_id": pid_s, "draft_id": str(did), "expected_edit_version": ver}
        q.update(expected_content_digest=dig, reason=a.reason)
        v = _dispatch(ctx, cmd, q)
        return _out(ctx, cmd, v, [f"published r{v.revision_no} ({v.revision_id})"], str(v.revision_id))
    v = _ask(ctx, cmd, _source_payload(ctx, plan_id, a))
    exported = json.dumps(_o.to_jsonable(v), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if a.output is None:
        return _out(ctx, cmd, v, exported.splitlines(), str(v.export_meta.content_digest))
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    atomic_write(Path(a.output), exported.encode("utf-8"), mode=0o600)
    return _out(ctx, cmd, v, [f"exported {v.export_meta.content_digest} to {a.output}"], str(a.output))


def _run_draft(a: argparse.Namespace, ctx: CliContext) -> int:  # noqa: PLR0912, PLR0915
    dverb, cmd, res = a.draft_verb, a.command_name, cast("Any", None)
    pid_s = str(plan_id := resolve_plan_id(ctx, a.plan, project_ref=a.project))
    if dverb == "open":
        res = _dispatch(ctx, cmd, {"plan_id": pid_s, "base": a.base})
        return _out(ctx, cmd, res, [f"opened draft {res.draft_id} (v{res.edit_version})"], str(res.draft_id))
    draft_id, ver = _resolve_draft_pair(ctx, plan_id, a.draft, getattr(a, "expected_version", None))
    did_s = str(draft_id)
    base: JsonObject = {"plan_id": pid_s, "draft_id": did_s, "expected_edit_version": ver}
    if dverb == "show":
        v = _ask(ctx, cmd, {"plan_id": pid_s, "draft_id": did_s})
        raw_s = json.dumps(_o.to_jsonable(v.document), indent=2, sort_keys=True, ensure_ascii=False)
        ln = raw_s.splitlines() if a.raw else _kv(ctx, v, "draft_id state edit_version stale document_digest")
        return _out(ctx, cmd, v, ln, str(v.draft_id))
    if dverb == "edit":
        cap_c = ErrorCode.CAPABILITY_UNAVAILABLE
        if a.format != "json":
            raise CapabilityUnavailable(cap_c, "only json format is supported", details={})
        view = _ask(ctx, "planning.get_draft", {"plan_id": pid_s, "draft_id": did_s})
        env = dict(ctx.environ) if isinstance(ctx, CliSession) else {}
        argv = resolve_editor({**env, **({"VISUAL": env["SKM_EDITOR"]} if env.get("SKM_EDITOR") else {})})
        tdir = None if isinstance(sdir := getattr(ctx, "state_dir", None), Path) else Path(tempfile.mkdtemp())
        dirs = [sdir / s for s in ("edits", "tmp")] if isinstance(sdir, Path) else [cast("Path", tdir)]
        pri, *_ = paths = [d / f"draft-{draft_id}.json" for d in dirs]
        init_b = f"{json.dumps(_o.to_jsonable(view.document), indent=2, ensure_ascii=False)}\n".encode()
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write(p, init_b, mode=0o600)
        status = subprocess.run([*argv, str(pri)], check=False).returncode
        raw_b = pri.read_bytes() if pri.is_file() else init_b
        for p in paths:
            atomic_write(p, raw_b, mode=0o600)
        h, det = f"your edit is kept in {pri}", {"path": str(pri), "hint": f"your edit is kept in {pri}"}
        if status != 0:
            raise CapabilityUnavailable(cap_c, f"editor exited with {status}", details=det)
        if raw_b != init_b:
            try:
                edited = json.loads(raw_b.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                iss: list[JsonValue] = [{"pointer": "", "code": "json", "message": str(exc)}]
                raise _bad("edited document is not valid JSON", path=str(pri), hint=h, issues=iss) from None
            if not isinstance(edited, dict):
                iss = [{"pointer": "", "code": "type", "message": "expected an object"}]
                raise _bad("the edited document must be a JSON object", path=str(pri), hint=h, issues=iss)
            ev = int(view.edit_version) if a.expected_version is None else a.expected_version
            q = {**base, "expected_edit_version": ev, "document": cast("JsonObject", edited)}
            try:
                res = _dispatch(ctx, cmd, q)
            except SkmError as err:
                object.__setattr__(err, "details", {**err.details, **det})
                raise
        for p in paths:
            p.unlink(missing_ok=True)
        if tdir is not None:
            shutil.rmtree(tdir, ignore_errors=True)
        if raw_b == init_b:
            nc = {"draft_id": did_s, "edit_version": int(view.edit_version), "changed": False}
            return _out(ctx, cmd, nc, ["no changes"], f"{did_s}:{view.edit_version}")
    elif dverb == "save":
        ld = _load_json(a.file)
        ch = ld.get("changes") if isinstance(ld, Mapping) else ld
        bad_s = (a.changes and not isinstance(ch, list)) or (not a.changes and not isinstance(ld, Mapping))
        if (a.patch and a.changes) or bad_s:
            raise _bad("invalid save flags or JSON payload")
        k = "changes" if a.changes else ("merge_patch" if a.patch else "document")
        res = _dispatch(ctx, cmd, {**base, k: ch if a.changes else dict(cast("Mapping[str, Any]", ld))})
    if dverb in ("edit", "save"):
        msg = f"saved draft {res.draft_id} (v{res.edit_version}, errors={res.counts.error})"
        return _out_findings(ctx, cmd, res, msg, f"{res.draft_id}:{res.edit_version}", res.findings)
    if dverb == "validate":
        v = _ask(ctx, cmd, {**base, "min_severity": a.severity})
        msg = f"draft {v.draft_id} (publishable={v.publishable}, errors={v.counts.error})"
        _out_findings(ctx, cmd, v, msg, "publishable" if v.publishable else "invalid", v.findings)
        bad = not v.publishable or int(v.counts.error) > 0 or bool(v.schema_issues) or bool(v.rule_failures)
        return _o.CLI_EXIT[ErrorCategory.VALIDATION] if bad else 0
    if dverb in ("publication-preview", "preview"):
        v = _ask(ctx, cmd, base)
        msg = f"candidate digest: {v.content_digest} (publishable={v.publishable})"
        return _out_findings(ctx, cmd, v, msg, str(v.content_digest), v.validation.findings)
    if dverb == "rebase":
        rl: list[JsonValue] = [{"conflict_id": k, "keep": s} for k, s in _parse_kv(a.resolves, "--resolve")]
        rl.extend({"conflict_id": k, "new_key": nk} for k, nk in _parse_kv(a.rekeys, "--rekey"))
        onto = str(resolve_revision_id(ctx, plan_id, a.onto)) if a.onto not in (None, "current") else None
        v = _dispatch(ctx, cmd, {**base, **_present(onto_revision_id=onto, resolutions=rl or None)})
        m = f"rebased draft {v.draft_id} (v{v.edit_version})"
        return _out(ctx, cmd, v, [m], f"{v.draft_id}:{v.edit_version}")
    if not (getattr(a, "yes", False) or ctx.assume_yes or ctx.confirm(f"Abandon draft {draft_id}?")):
        raise _bad("Confirmation required; pass --yes to confirm", reason="confirmation_required")
    v = _dispatch(ctx, cmd, base)
    return _out(ctx, cmd, v, [f"abandoned draft {v.draft_id}"], str(v.draft_id))


_D_OP: Final = {"show": "get_draft", "edit": "save_draft", "preview": "preview_publication"}
_T1: Final = {"list": "list_plans", "show": "get_plan", "entities": "list_entities", "text": "read_text"}
_T2: Final = {
    "revisions": "list_revisions",
    "diff": "diff_revisions",
    "preview": "ready_preview",
    "simulate": "simulate",
}
_T3: Final = {"stats": "plan_stats", "restore": "restore_revision", "publish": "publish_revision"}
_TOP_OP: Final = {"export": "export_specification", "import": "import_specification", **_T1, **_T2, **_T3}


def _register_draft(draft_parser: argparse.ArgumentParser) -> None:
    sub = draft_parser.add_subparsers(dest="draft_verb", required=True)
    for dv in ("open", "save", "validate", "rebase", "abandon", "publication-preview", *_D_OP):
        p = sub.add_parser(dv)
        op = "preview_publication" if dv == "publication-preview" else _D_OP.get(dv, f"{dv}_draft")
        p.set_defaults(run=_run_draft, command_name=f"planning.{op}")
        p.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        for arg in ("--project", "plan", *(() if dv == "open" else ("--draft",))):
            p.add_argument(arg)
        for f in ("--raw",) if dv == "show" else (("file", "--patch", "--changes") if dv == "save" else ()):
            p.add_argument(f, **({"action": "store_true"} if f.startswith("--") else {}))  # type: ignore[arg-type]
        if dv not in ("open", "show"):
            p.add_argument("--expected-version", type=int)
        if dv == "open":
            p.add_argument("--base", choices=("current", "empty"), default="current")
        elif dv == "edit":
            p.add_argument("--format", choices=("json", "toml"), default="json")
        elif dv == "validate":
            p.add_argument("--severity", choices=("error", "warning", "info"), default="warning")
        elif dv == "rebase":
            p.add_argument("--onto", default="current")
            p.add_argument("--resolve", dest="resolves", action="append")
            p.add_argument("--rekey", dest="rekeys", action="append")
        elif dv == "abandon":
            p.add_argument("--yes", default=argparse.SUPPRESS, action="store_true")


def _plan_research(args: argparse.Namespace, ctx: CliContext) -> int:
    plan_id = resolve_plan_id(ctx, args.plan, project_ref=args.project)
    result = run_host_research(ctx, {"action": "plan", "plan_id": str(plan_id), "spec": query_spec(args)})
    if not any(row["status"] == "ok" for row in result["results"]):
        _o.render_error(
            ctx,
            error_for(
                ErrorCode.RESEARCH_SOURCE_UNAVAILABLE,
                "No usable design research was retrieved",
                details={"results": result["results"]},
            ),
            command=args.command_name,
        )
        return 1
    ids = [row["query_id"] for row in result["results"] if row["status"] == "ok"]
    result["design_query_ids"] = ids
    refs = [f"research-query:{query_id}" for query_id in ids]
    return _out(ctx, args.command_name, result, [result["research_markdown"], *refs], " ".join(ids))


def register(sub: SubParsers) -> None:  # noqa: PLR0912, PLR0915
    parser = sub.add_parser("plan", help=GROUP.help)
    verbs = parser.add_subparsers(dest="plan_verb", required=True)
    for verb in (
        "create",
        "design",
        "approve",
        "list",
        "show",
        "entities",
        "text",
        "revisions",
        "diff",
        "preview",
        "simulate",
        "research",
        "stats",
        "archive",
        "restore",
        "publish",
        "export",
        "import",
        "draft",
    ):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb != "draft":
            command.set_defaults(run=_run_top, command_name=f"planning.{_TOP_OP.get(verb, f'{verb}_plan')}")
            command.add_argument("--project")
        if verb in ("show", "entities", "text", "revisions", "diff", "preview", "simulate", "research"):
            command.add_argument("plan")
        if verb == "approve":
            command.set_defaults(command_name="execution.approve_revision")
            command.add_argument("--reason", required=True)
        if verb in ("approve", "design", "stats", "archive", "restore", "publish", "export"):
            command.add_argument("plan")
        if verb == "approve":
            command.add_argument("report")
        if verb == "design":
            command.add_argument("file", help="brief JSON file, or - for standard input")
        if verb in ("show", "entities", "text", "preview", "simulate", "stats", "export"):
            command.add_argument("--revision")
        if verb in ("show", "entities", "text", "preview", "simulate", "stats", "export", "diff"):
            command.add_argument("--draft", nargs="?", const="open")
            command.add_argument("--expected-version", type=int)
        if verb == "create":
            for f in ("title", "--template"):
                command.add_argument(f)
            command.add_argument("--input", dest="inputs", action="append")
            command.add_argument("--no-draft", action="store_true")
        elif verb == "list":
            command.add_argument("--state", choices=("active", "archived", "all"), default="active")
        elif verb == "show":
            command.add_argument("--tree", action="store_true")
            command.add_argument("--entity")
            command.add_argument("--format", choices=("human", "json"), default="human")
        elif verb == "entities":
            for k in [("phase", "item", "unit", "requirement", "check", "criterion", "decision", "material")]:
                command.add_argument("--kind", dest="kinds", action="append", choices=k)
        elif verb == "text":
            for pos in ("target", "pointer"):
                command.add_argument(pos)
            command.add_argument("--offset-bytes", type=int, default=0)
            command.add_argument("--max-bytes", type=int, default=16384)
        elif verb == "revisions":
            command.add_argument("--before", type=int)
        elif verb == "diff":
            for pos in ("a", "b"):
                command.add_argument(pos, nargs="?")
        elif verb == "preview":
            for flag in ("--assume-done", "--assume-granted"):
                command.add_argument(flag, action="append")
            command.add_argument("--limit", type=int, default=8)
        elif verb == "simulate":
            command.add_argument("--tokens-per-second", type=int, help="assumed effective model throughput")
        elif verb == "research":
            command.set_defaults(run=_plan_research, command_name="context.host.research_query")
            command.add_argument("text", help="research question")
            command.add_argument("--source", action="append", help="source id (repeatable)")
            command.add_argument("--deep", action="store_true", help="allow configured deep research")
            command.add_argument("--max-documents", type=int, default=10, help="maximum documents per source")
            command.add_argument("--no-cache", action="store_true", help="bypass research cache")
            command.add_argument(
                "--save-as-material", action="store_true", help="capture retrieved documents"
            )
        elif verb == "archive":
            command.add_argument("--yes", default=argparse.SUPPRESS, action="store_true")
        elif verb == "restore":
            command.add_argument("rev", nargs="?")
            command.add_argument("--revision", dest="revision_opt", type=int)
            command.add_argument("--expected-current")
        elif verb == "publish":
            for f in ("--draft", "--expected-content-digest"):
                command.add_argument(f)
        elif verb == "import":
            for flag in ("file", "--plan", "--base", "--title", "--materials"):
                command.add_argument(flag)
            command.add_argument("--as", dest="as_mode", choices=("new-plan", "new-draft"))
            for flag in ("--new-plan", "--new-draft", "--keep-ids", "--remap-ids"):
                command.add_argument(flag, action="store_true")
            command.add_argument("--rebind", dest="rebinds", action="append")
        elif verb == "draft":
            _register_draft(command)
        if verb in ("archive", "publish"):
            command.add_argument("--expected-version", type=int)
        if verb in ("restore", "publish"):
            command.add_argument("--reason", required=True)
        if verb in ("list", "entities", "export"):
            command.add_argument("--output" if verb == "export" else "--after")
        if verb in ("list", "entities", "revisions"):
            command.add_argument("--limit", type=int, default=50)
            command.add_argument("--all", action="store_true")


GROUP: Final = CommandGroup("plan", _HELP["draft"], register, module="planning", order=30)
