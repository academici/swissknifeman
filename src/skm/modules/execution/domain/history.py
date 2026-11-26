"""Pure versioned bounded causality history builder v1 (execution §8.1, §9)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "BUILDER_VERSION",
    "MAX_ENTRY_EDGES",
    "MAX_ENTRY_NODES",
    "MAX_PAGE_BYTES",
    "MAX_PAGE_EDGES",
    "MAX_PAGE_EVENTS",
    "MAX_PAGE_NODES",
    "build_history",
]

BUILDER_VERSION: Final = 1
MAX_PAGE_EVENTS, MAX_PAGE_NODES, MAX_PAGE_EDGES, MAX_PAGE_BYTES = 200, 1600, 3200, 1_048_576
MAX_ENTRY_NODES, MAX_ENTRY_EDGES, _MAX_ENTRY_BYTES = 32, 200, 262_144
_NIL_UUID, _OBS_URN = "00000000-0000-0000-0000-000000000000", "urn:skm:runtimes:runtime-observation:v1"
_COV_RANK: Final = {"complete": 0, "partial": 1, "unavailable": 2}
_PAT_S = (
    r"uuid=^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|digest=^sha256:[0-9a-f]{64}$|"
    r"rule=^[A-Z][A-Za-z0-9_]{0,31}$|code=^[A-Z][A-Z0-9_]{0,63}$|cmd=^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$|"
    r"urn=^urn:skm:[a-z][a-z0-9-]*:event:[a-z][a-z0-9-]*:v[1-9][0-9]*$"
)
_PAT: Final = {k: re.compile(v) for s in _PAT_S.split("|") for k, v in (s.split("=", 1),)}
_VOC_S = (
    "run=created ready running waiting paused succeeded failed cancelled;step=started succeeded failed "
    "cancelled;task=blocked ready assigned executing checking manual_pending reviewing rework_required "
    "awaiting_decision integrating accepted failed cancelled superseded skipped;attempt=preparing running "
    "waiting submitted completed ownership_lost abandoned;stage=started context_draft running completed "
    "failed interrupted skipped;check=pending running passed failed manual_pending error cancelled unknown;"
    "review=started completed failed;decision_request=open answered applied assumed denied stale expired "
    "cancelled;decision=applied superseded;effect=intended executing succeeded failed outcome_unknown;"
    "output=sealed;fix_brief=sealed;finding=open confirmed rejected resolved waived deferred;"
    "reconfiguration=applied;recovery=running completed failed not_needed"
)
_VOCAB: Final = {k: frozenset(v.split()) for s in _VOC_S.split(";") for k, v in (s.split("="),)}
_SET_S = (
    "role=scout executor reviewer triager advisor researcher registrar;stg=stage step output recovery "
    "effect;mode=normal retry rework final_correction continue_with_answer resume_interrupted "
    "retriage_with_advice reconcile;binding_consistency=matched mismatch unavailable;basis=db_transition "
    "host_monotonic provider_claim unknown;task_kind=unit item item_gate phase_gate plan_acceptance "
    "integration followup group_review plan_audit;trig=manual_start dependency_satisfied stage_outcome "
    "check_failed review_findings retry lease_recovery operator_resume reconfigure observation run_start "
    "followup integration wait_changed monitor policy_resolved carry_forward cancel timeout timer "
    "subscription restart skip decision_answered manual_verdict;nodelta=assignment-leased lease-expired "
    "budget-exhausted recovery-circuit-opened review-requested readiness-reported autopilot-state-changed;"
    "att=attempt stage step output check review fix_brief recovery effect;id_opt=plan_revision_id "
    "entity_id task_id attempt_id stage_record_id;run_ev=run-started:running run-resumed:running "
    "run-paused:paused run-waiting:waiting run-cancelled:cancelled;tev=task-created task-ready task-failed "
    "task-skipped task-accepted task-assigned task-rework-required task-wait-changed followups-created"
)
_SETS: Final = {k: frozenset(v.split()) for s in _SET_S.split(";") for k, v in (s.split("="),)}
_RUN_ST: Final[dict[str, str]] = {k: v for s in _SETS["run_ev"] for k, v in (s.split(":"),)}
_PAT_OPT: Final = {"reason_code": "code", "advance_rule": "rule", "input_digest": "digest"}
_COL_S = (
    "route=requested resolved route_source host_id executable_sha256 verification_key "
    "effective_config_digest reconfiguration_ids route_reason runtime_version adapter_version "
    "catalog_digest profile_version_id;obind=runtime_id runtime_version adapter_version executable_sha256 "
    "verification_key provider_reported_model model_source;otime=clock_domain_id duration_ms "
    "first_observed_at last_observed_at provider_first_at provider_last_at;ocap=coverage bytes_seen "
    "bytes_retained bytes_dropped truncated gaps parser_flags live_events_dropped;mon=evaluation_id "
    "monitor_id rule_id rule_version target_stage_record_id fencing_token thresholds config_digest "
    "input_watermark input_coverage last_signal_at scheduled_at started_at finished_at verdict action "
    "action_request_id recovery_record_id reason_code config_generation recovery_mode"
)
_COLS: Final = {k: tuple(v.split()) for s in _COL_S.split(";") for k, v in (s.split("="),)}
_TIMING_K = "started_at finished_at duration_ms clock_domain_id basis"
_PAGE_K = "run_id through_seq builder_version scanned_through_seq entries next_after coverage"
_UNREP_K = ("seq", "event_id", "event_type", "occurred_at", "recorded_at")
type _Map = Mapping[str, JsonValue]
type _Pair = tuple[str, str]
type _RefSet = frozenset[_Pair]
type _Refs = tuple[set[_Pair], _RefSet | None, _RefSet, _RefSet]


def _kv(keys: str, vals: Sequence[JsonValue]) -> dict[str, JsonValue]:
    return dict(zip(keys.split(), vals, strict=True))


def _cmax(a: str, b: str) -> str:
    return max(a, b, key=_COV_RANK.__getitem__)


def _cbytes(v: JsonValue) -> int:
    return len(json.dumps(v, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode())


def _as_map(val: object) -> _Map | None:
    return cast("_Map", val) if isinstance(val, Mapping) else None


def _as_seq(val: object) -> Sequence[JsonValue] | None:
    return cast("Sequence[JsonValue]", val) if isinstance(val, list | tuple) else None


def _tok(kind: str, val: object) -> str | None:
    s = (val.lower() if kind == "uuid" else val) if isinstance(val, str) else None
    return s if s is not None and _PAT[kind].fullmatch(s) else None


def _opt(doc: dict[str, JsonValue], **kw: object) -> None:
    enum_k = {"role", "mode", "task_kind", "binding_consistency"}
    for k, v in kw.items():
        if isinstance(v, str) and ((k in enum_k and v in _SETS[k]) or k in _SETS["id_opt"]):
            doc[k] = v
        elif (pat := _PAT_OPT.get(k)) and (fv := _tok(pat, v)):
            doc[k] = fv
        elif k == "round_no" and isinstance(v, int) and not isinstance(v, bool) and v >= 1:
            doc[k] = v
        elif k in {"route_snapshot", "timing"} and (mv := _as_map(v)) is not None:
            doc[k] = dict(mv)


class _ProjCtx:
    def __init__(self, rid: str, s: str, p: _Map, b: dict[str, JsonValue], r: _Refs) -> None:
        self.run_id, self.short, self.payload, self.base = rid, s, p, b
        self.page_seen, self.known_local, self.auth_foreign, self.exp_foreign = r
        self.entry_local, self.restricted, self.cov = set[_Pair](), False, "complete"
        self.ar: str | None = None
        self.tid, self.aid, self.srid = self.u("task_id"), self.u("attempt_id"), self.u("stage_record_id")
        self.nodes, self.edges, self.reasons = list[JsonObject](), list[JsonObject](), list[str]()

    def u(self, *keys: str) -> str | None:
        return next((v for k in keys if (v := _tok("uuid", self.payload.get(k)))), None)

    def is_foreign(self, k: str, eid: str) -> bool:
        kl, seen = self.known_local, self.page_seen | self.entry_local
        return (k, eid) in self.exp_foreign or (kl is not None and (k, eid) not in (kl | seen))

    def endpoint(self, k: str, eid: str, *, foreign: bool = False) -> JsonObject:
        if foreign or self.is_foreign(k, eid):
            if (k, eid) in self.auth_foreign:
                return _kv("kind id visibility", (k, eid, "unloaded"))
            self.restricted = True
            return _kv("kind visibility", (k, "foreign_opaque"))
        vis = "local" if (k, eid) in (self.page_seen | self.entry_local) else "unloaded"
        return _kv("kind id visibility", (k, eid, vis))

    def deg(self, code: str = "LEGACY_FIELDS_MISSING", lv: str = "partial") -> bool:
        self.cov = _cmax(self.cov, lv)
        self.reasons.append(code)
        return True

    def add(self, k: str, eid: str, st: object = None, par: _Pair | None = None, **kw: object) -> JsonObject:
        self.entry_local.add((k, eid))
        rel, drel, cov_s = kw.pop("rel", None), kw.pop("drel", None), str(kw.pop("cov", None) or "complete")
        doc = _kv("ref coverage", (_kv("kind id visibility", (k, eid, "local")), cov_s))
        if par is not None:
            doc["parent"] = self.endpoint(*par)
        if isinstance(st, str) and st in _VOCAB.get(k, frozenset()):
            doc["state"] = st
        td = None if k in {"run", "reconfiguration"} else self.tid
        ad, sd = (self.aid if k in _SETS["att"] else None), (self.srid if k in _SETS["stg"] else None)
        ard = self.ar if k in {"run", "task", "stage"} else None
        _opt(doc, **{"task_id": td, "attempt_id": ad, "stage_record_id": sd, "advance_rule": ard, **kw})
        self.nodes.append(doc)
        if isinstance(rel, str) and par is not None:
            self.edge(rel, par, (k, eid))
        if isinstance(drel, str) and par is not None:
            self.edge(drel, (k, eid), par)
        return doc

    def edge(self, k: str, src: _Pair, dst: _Pair, *, dst_foreign: bool = False) -> None:
        ep_dst = self.endpoint(*dst, foreign=dst_foreign)
        self.edges.append(_kv("kind source target", (k, self.endpoint(*src), ep_dst)))

    def lmap(self, src: _Pair, m: _Map, spec: str, cap: int = 32) -> None:
        for item in spec.split():
            k, ek, nk = item.split(":")
            raw = m.get(k)
            for x in raw[:cap] if isinstance(raw, list | tuple) else (raw,):
                if (uid := _tok("uuid", x)) is not None:
                    self.edge(ek, src, (nk, uid))

    @staticmethod
    def route(raw: object) -> JsonObject | None:
        m, rkeys = _as_map(raw), _COLS["route"]
        req, res = (_as_map(m.get("requested")), _as_map(m.get("resolved"))) if m else (None, None)
        rc = _as_seq(m.get("reconfiguration_ids")) if m else None
        if m is None or req is None or res is None or rc is None or not all(k in m for k in rkeys):
            return None
        out: dict[str, JsonValue] = {k: m[k] for k in rkeys[2:] if k != "reconfiguration_ids"}
        out["requested"] = {k: req.get(k) for k in ("runtime_id", "model", "model_class", "effort")}
        out["resolved"] = {k: res.get(k) for k in ("runtime_id", "model", "effort")}
        for name in ("requested_route", "selected_route"):
            if projected := _as_map(m.get(name)):
                out[name] = {k: projected.get(k) for k in ("runtime_id", "model", "effort")}
        out["reconfiguration_ids"] = [u for x in rc[:128] if (u := _tok("uuid", x))]
        return out if _cbytes(out) <= 16384 else None

    @staticmethod
    def obs(raw: object) -> tuple[JsonObject | None, bool]:
        if raw is None:
            return None, True
        m = _as_map(raw)
        req_id = _tok("uuid", m.get("request_id")) if m else None
        subs = [_as_map(m.get(k)) for k in ("binding", "timing", "capture", "tools")] if m else [None]
        if m is None or m.get("schema") != _OBS_URN or not req_id or any(x is None for x in subs):
            return None, False
        b, tm, cap, tl = (cast("_Map", x) for x in subs)
        ok = all(k in b for k in _COLS["obind"]) and all(k in tm for k in _COLS["otime"][:4])
        if not (ok and all(k in cap for k in _COLS["ocap"]) and {"coverage", "observed_calls"} <= tl.keys()):
            return None, False
        if str(b.get("provider_reported_model") or "").startswith("secret://"):
            return None, False
        bd, cd = {k: b[k] for k in _COLS["obind"]}, {k: cap[k] for k in _COLS["ocap"]}
        if "observed_effort" in b:
            bd["observed_effort"] = b["observed_effort"]
        td = {k: tm[k] for k in _COLS["otime"] if k in tm}
        tld = _kv("coverage observed_calls", (tl["coverage"], tl["observed_calls"]))
        out = _kv("schema request_id binding timing capture tools", (_OBS_URN, req_id, bd, td, cd, tld))
        return (out, True) if _cbytes(cast("JsonValue", m)) <= 16384 else (None, False)

    @staticmethod
    def timing(m: _Map | None, k_sa: str, k_fa: str, basis: str) -> JsonObject | None:
        if m is None or basis not in _SETS["basis"]:
            return None
        dur, sa_r, fa_r = m.get("duration_ms"), m.get(k_sa), m.get(k_fa)
        dm = dur if isinstance(dur, int) and not isinstance(dur, bool) and dur >= 0 else None
        sa, fa = (sa_r if isinstance(sa_r, str) else None), (fa_r if isinstance(fa_r, str) else None)
        return _kv(_TIMING_K, (sa, fa, dm, _tok("uuid", m.get("clock_domain_id")), basis))

    def cause(self, raw: object) -> tuple[JsonObject | None, bool]:
        if raw is None:
            return None, True
        m = _as_map(raw)
        if m is None or not isinstance(tk := m.get("trigger_kind"), str) or tk not in _SETS["trig"]:
            return None, False
        adv_raw, rc_raw = m.get("advance_rule"), _as_seq(m.get("reason_codes", ()))
        refs_raw, adv = _as_seq(m.get("refs", ())), (_tok("rule", adv_raw) if adv_raw is not None else None)
        bad_adv = adv_raw is not None and (adv is None or tk == "observation")
        if bad_adv or rc_raw is None or refs_raw is None:
            return None, False
        rcs = [_tok("code", item) for item in rc_raw[:32]]
        if any(x is None for x in rcs):
            return None, False
        refs: list[JsonValue] = []
        for ref_val in refs_raw[:200]:
            ref = _as_map(ref_val)
            rk, rid = (ref.get("kind"), _tok("uuid", ref.get("id"))) if ref else (None, None)
            if not isinstance(rk, str) or rk not in _VOCAB or rid is None or ref is None:
                return None, False
            is_f = bool(ref.get("foreign", False)) or self.is_foreign(rk, rid)
            if is_f and (rk, rid) not in self.auth_foreign:
                self.restricted = True
            else:
                refs.append(_kv("kind id", (rk, rid)))
        out = _kv("trigger_kind advance_rule reason_codes refs", (tk, adv, [x for x in rcs if x], refs))
        for k, pat in (("command_id", "cmd"), ("source_event_id", "uuid")):
            if (v := _tok(pat, m.get(k))) is not None:
                out[k] = v
        return out, True


def _p_run_task(c: _ProjCtx) -> bool:  # noqa: PLR0912
    p, tid, s, rpar = c.payload, c.tid, c.short, ("run", c.run_id)
    if s == "run-reconfigured":
        rec = c.u("reconfiguration_id")
        ok = bool(rec and c.add("reconfiguration", rec, "applied", rpar, rel="contains"))
        return ok or c.deg(lv="unavailable")
    if s in _RUN_ST or s in {"run-created", "run-finished"}:
        st_f = _RUN_ST.get(s) or str(p.get("outcome", "succeeded"))
        st = str(p.get("status", "created")) if s == "run-created" else st_f
        rev_id, rc = c.u("revision_id"), p.get("stop_code") or p.get("previous_stop_code")
        if s == "run-created" and rev_id is None:
            c.deg()
        return bool(c.add("run", c.run_id, st, cov=c.cov, plan_revision_id=rev_id, reason_code=rc))
    if s not in _SETS["tev"]:
        return False
    if tid is None:
        return c.deg(lv="unavailable")
    if s == "task-created":
        tkind, init_st = p.get("kind"), p.get("initial_state")
        if tkind not in _SETS["task_kind"] or not (isinstance(init_st, str) and init_st in _VOCAB["task"]):
            c.deg()
        par, orig = (("task", pt) if (pt := c.u("parent_task_id")) else rpar), _as_map(p.get("origin"))
        n = c.add("task", tid, init_st, par, rel="contains", cov=c.cov, task_kind=tkind)
        _opt(n, plan_revision_id=c.u("revision_id"), entity_id=c.u("entity_id"))
        if orig:
            _opt(n, reason_code=orig.get("reason_code"))
            for key, nk in (("source_task_id", "task"), ("review_id", "review")):
                if oid := _tok("uuid", orig.get(key)):
                    c.edge("triggers", (nk, oid), ("task", tid))
    elif s in {"task-ready", "task-failed", "task-skipped"}:
        rc = p.get("code") if s == "task-failed" else None
        c.add("task", tid, s[5:], rpar, cov=c.cov, attempt_id=c.aid, reason_code=rc)
    elif s == "task-accepted":
        c.add("task", tid, "accepted", attempt_id=c.aid)
        cl_src = _tok("uuid", (_as_map(p.get("clearance")) or {}).get("source_task_id"))
        if bool(p.get("carried_forward", False)) and (src_t := c.u("source_task_id") or cl_src):
            c.edge("reuses", ("task", tid), ("task", src_t), dst_foreign=True)
        elif oid := c.u("output_id"):
            c.edge("approved_by", ("output", oid), ("task", tid))
    elif s == "task-assigned":
        if c.aid is None:
            return c.deg(lv="unavailable")
        c.add("task", tid, "assigned", rpar)
        c.add("attempt", c.aid, str(p.get("attempt_state", "preparing")), ("task", tid), rel="contains")
        c.lmap(("attempt", c.aid), p, "previous_attempt_id:supersedes:attempt")
    elif s == "task-rework-required":
        tn = c.add("task", tid, "rework_required", attempt_id=c.aid)
        _opt(tn, round_no=p.get("round"), reason_code=p.get("reason"))
        if fb_id := c.u("fix_brief_id"):
            c.add("fix_brief", fb_id, "sealed", ("task", tid), rel="contains")
            c.lmap(("fix_brief", fb_id), p, "input_output_id:reworks:output")
    elif s == "task-wait-changed":
        if "previous_code" not in p or "code" not in p:
            return c.deg(lv="unavailable")
        sa, fa = (p[k] if isinstance(p.get(k), str) else None for k in ("started_at", "finished_at"))
        wvals = (_tok("code", p.get("previous_code")), _tok("code", p.get("code")), sa, fa)
        c.base["wait"] = _kv("previous_code code started_at finished_at", wvals)
        c.add("task", tid, p.get("state"), rpar, cov=c.cov, attempt_id=c.aid, reason_code=p.get("code"))
    elif _as_seq(p.get("followup_task_ids", ())) is None:
        return c.deg(lv="unavailable")
    else:
        c.add("task", tid, "blocked")
        c.lmap(("task", tid), p, "followup_task_ids:triggers:task", MAX_ENTRY_EDGES)
    return True


def _p_stage_obs(c: _ProjCtx) -> bool:
    if c.short not in {"stage-started", "stage-completed", "step-observation-recorded"}:
        return False
    p = c.payload
    if c.tid is None or c.aid is None or c.srid is None:
        return c.deg(lv="unavailable")
    srid, sg = c.srid, ("stage", c.srid)
    if c.short == "step-observation-recorded":
        if (stid := c.u("step_id")) is None:
            return c.deg(lv="unavailable")
        obs, obs_ok = c.obs(p.get("observation"))
        if not obs_ok:
            return c.deg("PAYLOAD_UNREPRESENTABLE", "unavailable")
        sp = ("step", ps) if (ps := c.u("parent_step_id")) else sg
        rs, bc_r = c.route(p.get("route_snapshot")), p.get("binding_consistency")
        bc = bc_r if isinstance(bc_r, str) and bc_r in _SETS["binding_consistency"] else "unavailable"
        cc = str((_as_map(obs.get("capture")) or {}).get("coverage", "complete")) if obs else "unavailable"
        tc = str((_as_map(obs.get("tools")) or {}).get("coverage", "complete")) if obs else "unavailable"
        unav = (obs is None or cc == "unavailable") and c.deg("OBSERVATION_UNAVAILABLE")
        ncov = "unavailable" if unav else ("partial" if cc == "partial" or tc != "complete" else "complete")
        c.cov = _cmax(c.cov, ncov)
        d1 = bc == "mismatch" and c.deg("BINDING_MISMATCH")
        if (rs is None and p.get("route_snapshot") is not None and c.deg()) or d1:
            ncov = _cmax(ncov, "partial")
        ot = _as_map(obs.get("timing")) if obs else None
        tb = "host_monotonic" if ot and ot.get("duration_ms") is not None else "unknown"
        n = c.add("step", stid, None, sp, rel="observed_by", cov=ncov, role=p.get("role"))
        _opt(n, route_snapshot=rs, timing=c.timing(ot, "first_observed_at", "last_observed_at", tb))
        _opt(n, binding_consistency=bc)
        n["runtime_observation"] = None if obs is None else dict(obs)
        return True
    if c.short == "stage-started":
        if (in_dig := _tok("digest", p.get("input_digest"))) is None:
            c.deg()
        n = c.add("stage", srid, "started", ("attempt", c.aid), rel="contains", cov=c.cov, mode=p.get("mode"))
        _opt(n, round_no=p.get("round_no"), input_digest=in_dig)
        c.lmap(sg, p, "retry_of_id:retries:stage input_output_id:consumes:output")
        c.lmap(sg, p, "reconfiguration_ids:consumes:reconfiguration", 64)
        if fb := _as_map(p.get("feedback_refs")):
            c.lmap(sg, fb, "fix_brief_id:reworks:fix_brief advice_step_id:consumes:step")
            c.lmap(sg, fb, "schema_errors_step_id:consumes:step interrupted_stage_record_id:retries:stage")
            c.lmap(sg, fb, "answer_request_ids:consumes:decision_request")
        for raw_sr in (_as_seq(p.get("step_refs", ())) or ())[:8]:
            if (sr := _as_map(raw_sr)) and (stid := _tok("uuid", sr.get("step_id"))):
                sp = ("step", ps) if (ps := _tok("uuid", sr.get("parent_step_id"))) else sg
                rs = c.route(sr.get("route_snapshot"))
                sc = "complete" if rs or "route_snapshot" not in sr else "partial"
                sn = c.add("step", stid, "started", sp, rel="contains", cov=sc)
                _opt(sn, role=sr.get("role"), route_snapshot=rs)
        return True
    raw_st, ok = p.get("state"), str(p.get("outcome_kind", ""))
    if not (isinstance(raw_st, str) and raw_st in _VOCAB["stage"]):
        st_m = {"cancelled": "interrupted", "skipped": "skipped"}
        raw_st = "failed" if ok in {"runtime_error", "result_invalid"} else st_m.get(ok, "completed")
    scov = sc if (sc := str(p.get("coverage", "complete"))) in _COV_RANK else "complete"
    c.cov, tm = _cmax(c.cov, scov), _as_map(p.get("timing"))
    tb = str(b) if tm and isinstance(b := tm.get("basis", "db_transition"), str) else ""
    n = c.add("stage", srid, str(raw_st), ("attempt", c.aid), cov=scov, mode=p.get("mode"))
    rc, st_tm = p.get("reason_code") or p.get("error_code"), c.timing(tm, "started_at", "finished_at", tb)
    _opt(n, round_no=p.get("round_no"), reason_code=rc, timing=st_tm)
    c.lmap(sg, p, "reused_from_step_id:reuses:step output_id:produces:output")
    c.lmap(sg, p, "check_execution_ids:produces:check review_ids:produces:review effect_ids:produces:effect")
    m_ss = _as_map(ss := p.get("step_states"))
    seq_items = [(i.get("step_id"), i.get("state")) for r in (_as_seq(ss) or ()) if (i := _as_map(r))]
    for rk, rv in (list(m_ss.items()) if m_ss is not None else seq_items)[: MAX_ENTRY_NODES - 1]:
        if (u := _tok("uuid", rk)) and isinstance(rv, str) and rv in _VOCAB["step"]:
            c.add("step", u, rv, sg, rel="contains")
    return True


def _p_attempt_io(c: _ProjCtx) -> bool:
    p, s = c.payload, c.short
    par_h = ("stage", c.srid) if c.srid else (("attempt", c.aid) if c.aid else ("run", c.run_id))
    if s in {"attempt-started", "attempt-ownership-lost"}:
        st = "running" if s == "attempt-started" else "ownership_lost"
        ok_a = bool(c.tid and c.aid and c.add("attempt", c.aid, st, ("task", c.tid)))
        return ok_a or c.deg(lv="unavailable")
    if s == "runtime-start-admitted":
        b = _as_seq(p.get("step_bindings", ()))
        if not (c.tid and c.aid and c.srid) or b is None:
            return c.deg(lv="unavailable")
        if not b:
            c.reasons.append("NO_HISTORY_DELTA")
        for r in b[:8]:
            if (it := _as_map(r)) and (stid := _tok("uuid", it.get("step_id"))):
                c.add("step", stid, "started", ("stage", c.srid))
        return True
    if s == "stage-recovered":
        rid = c.u("recovery_record_id", "recovery_id")
        st = sv if (sv := str(p.get("state", "completed"))) in _VOCAB["recovery"] else "completed"
        rc = p.get("reason_code") or p.get("outcome")
        ok_r = bool(rid and c.add("recovery", rid, st, par_h, drel="evaluates", reason_code=rc))
        return ok_r or c.deg(lv="unavailable")
    if s == "output-sealed":
        if not (oid := c.u("output_id")) or not c.aid:
            return c.deg(lv="unavailable")
        par = ("stage", c.srid) if c.srid else ("attempt", c.aid)
        c.add("output", oid, "sealed", par, input_digest=p.get("manifest_digest"))
        c.edge("produces", ("step", sid) if (sid := c.u("step_id")) else par, ("output", oid))
        return True
    if s in {"external-effect-recorded", "external-effect-outcome-unknown", "integration-completed"}:
        rs = _as_seq(p.get("integration_receipts", ())) if s == "integration-completed" else None
        r0 = _as_map(rs[0]) if rs else None
        efid = c.u("effect_id") or (_tok("uuid", r0.get("effect_id")) if r0 else None)
        def_st = "succeeded" if s == "integration-completed" else str(p.get("state", "intended"))
        eff_st = "outcome_unknown" if s == "external-effect-outcome-unknown" else def_st
        return bool(efid and c.add("effect", efid, eff_st, par_h, rel="produces")) or c.deg(lv="unavailable")
    return False


def _p_verdict_decision(c: _ProjCtx) -> bool:  # noqa: PLR0911
    p, s = c.payload, c.short
    par_h = ("stage", c.srid) if c.srid else (("attempt", c.aid) if c.aid else ("run", c.run_id))
    if s in {"check-completed", "manual-verdict-recorded"}:
        if not (cid := c.u("check_execution_id")):
            return c.deg(lv="unavailable")
        oid, is_mv = c.u("output_id"), s == "manual-verdict-recorded"
        st = "passed" if p.get("verdict") == "pass" else "failed"
        c.add("check", cid, st if is_mv else str(p.get("state", "passed")), ("output", oid) if oid else par_h)
        c.lmap(("check", cid), p, "output_id:evaluates:output reused_from_id:reuses:check")
        if is_mv and (vid := c.u("verdict_id")):
            c.add("decision", vid, "applied", ("check", cid), rel="approved_by")
            c.lmap(("decision", vid), p, "supersedes_verdict_id:supersedes:decision")
        return True
    if s == "review-completed":
        if not (rid := c.u("review_id")) or not c.tid:
            return c.deg(lv="unavailable")
        par = ("output", oid) if (oid := c.u("output_id")) else ("task", c.tid)
        c.add("review", rid, "completed", par, round_no=p.get("round_no"))
        c.lmap(("review", rid), p, "output_id:evaluates:output")
        for rf in (_as_seq(p.get("finding_ids", ())) or ())[: MAX_ENTRY_NODES - 1]:
            if fid := _tok("uuid", rf):
                c.add("finding", fid, "open", ("review", rid), rel="produces")
        return True
    if s in {"acceptance-decided", "deviation-accepted"}:
        is_acc = s == "acceptance-decided"
        if not c.tid or not (did := c.u("acceptance_decision_id" if is_acc else "deviation_id")):
            return c.deg(lv="unavailable")
        aid = c.aid if is_acc else None
        c.add("decision", did, "applied", ("task", c.tid), rel="contains", attempt_id=aid)
        if is_acc:
            c.lmap(("decision", did), p, "output_id:evaluates:output")
        elif fid := c.u("finding_id"):
            c.add("finding", fid, "waived")
            c.edge("approved_by", ("finding", fid), ("decision", did))
        return True
    if s in {"decision-requested", "decision-answered"}:
        if not (drid := c.u("request_id", "decision_request_id")):
            return c.deg(lv="unavailable")
        par, is_req = (("task", c.tid) if c.tid else ("run", c.run_id)), s == "decision-requested"
        st, rel = str(p.get("state", "open" if is_req else "answered")), ("contains" if is_req else None)
        _opt(c.add("decision_request", drid, st, par, rel=rel), reason_code=p.get("code"))
        if not is_req and (rec_id := c.u("decision_record_id")):
            c.add("decision", rec_id, "applied", ("decision_request", drid), rel="produces")
        return True
    return False


def _unrep(base: _Map, code: str) -> JsonObject:
    u = _kv("nodes edges coverage reason_codes", ([], [], "unavailable", [code]))
    return {**{k: base[k] for k in _UNREP_K}, **u}


def _project_event(rid: str, seq: int, ev: JsonObject, refs: _Refs) -> tuple[JsonObject, set[_Pair], int]:
    ev_id = _tok("uuid", ev.get("id", ev.get("event_id"))) or _NIL_UUID
    raw_et = str(ev.get("event_type", "urn:skm:execution:event:unknown:v1"))
    ev_type = raw_et if _PAT["urn"].fullmatch(raw_et) else "urn:skm:execution:event:unknown:v1"
    occ_at = str(ev.get("occurred_at") or ev.get("recorded_at") or "1970-01-01T00:00:00Z")
    rec_at, p = str(ev.get("recorded_at") or occ_at), _as_map(ev.get("payload"))
    pfx = "urn:skm:execution:event:"
    base = _kv("seq event_id event_type occurred_at recorded_at", (seq, ev_id, ev_type, occ_at, rec_at))
    if p is None or not ev_type.startswith(pfx) or not ev_type.endswith(":v1"):
        ur = _unrep(base, "PAYLOAD_UNREPRESENTABLE" if p is None else "UNSUPPORTED_EVENT_TYPE")
        return ur, set[_Pair](), _cbytes(ur)
    ef = set[_Pair]()
    for r in _as_seq(ev.get("foreign_refs")) or ():
        if (m := _as_map(r)) and isinstance(m.get("kind"), str) and (u := _tok("uuid", m.get("id"))):
            ef.add((str(m["kind"]), u))
    ctx = _ProjCtx(rid, ev_type[len(pfx) : -3], p, base, (refs[0], refs[1], refs[2], refs[3] | ef))
    cause_doc, cause_ok = ctx.cause(p.get("cause"))
    ctx.ar = _tok("rule", cause_doc.get("advance_rule")) if cause_doc else None
    if not cause_ok:
        ctx.deg("LEGACY_FIELDS_MISSING")
    elif cause_doc is not None:
        base["cause"] = cause_doc
    if ctx.short in _SETS["nodelta"]:
        ctx.reasons.append("NO_HISTORY_DELTA")
    elif ctx.short == "monitor-evaluated":
        if all(k in p for k in _COLS["mon"]) and _as_seq(p.get("thresholds")) is not None:
            ctx.base["monitor_evaluation"] = {k: p[k] for k in _COLS["mon"]}
            if (ic := str(p.get("input_coverage", "complete"))) in _COV_RANK:
                ctx.cov = _cmax(ctx.cov, ic)
            ctx.reasons.append("NO_HISTORY_DELTA")
        else:
            ctx.deg(lv="unavailable")
    elif not any(fn(ctx) for fn in (_p_run_task, _p_stage_obs, _p_attempt_io, _p_verdict_decision)):
        ctx.deg("UNSUPPORTED_EVENT_TYPE", "unavailable")
    if ctx.restricted:
        ctx.deg("FOREIGN_REFERENCE_RESTRICTED")
    ns, es = list[JsonValue](ctx.nodes), list[JsonValue](ctx.edges)
    rcs = list[JsonValue](dict.fromkeys(ctx.reasons))
    base.update(_kv("nodes edges coverage reason_codes", (ns, es, ctx.cov, rcs)))
    eb = _cbytes(base)
    if len(ns) > MAX_ENTRY_NODES or len(es) > MAX_ENTRY_EDGES or eb > _MAX_ENTRY_BYTES:
        ur = _unrep(base, "PAYLOAD_UNREPRESENTABLE")
        return ur, set[_Pair](), _cbytes(ur)
    return base, ctx.entry_local, eb


def build_history(  # noqa: PLR0913
    events: Sequence[JsonObject],
    through_seq: int,
    *,
    run_id: str | None = None,
    after_seq: int = 0,
    limit: int = MAX_PAGE_EVENTS,
    known_local_ids: _RefSet | None = None,
    authorized_foreign_ids: _RefSet | None = None,
    explicit_foreign_ids: _RefSet | None = None,
    encode_cursor: Callable[[int], str] | None = None,
) -> JsonObject:
    """Build a bounded ``HistoryPage`` v1 strictly from immutable run ``domain_events``."""
    bad = isinstance(through_seq, bool) or through_seq < 0 or isinstance(after_seq, bool) or after_seq < 0
    if bad or after_seq > through_seq or isinstance(limit, bool) or limit < 1:
        det = _kv("through_seq after_seq limit", (through_seq, after_seq, limit))
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid run history bounds", details=det)
    rid = _tok("uuid", run_id)
    for ev in () if rid else events:
        pl = _as_map(ev.get("payload")) or {}
        if rid := _tok("uuid", ev.get("stream_id")) or _tok("uuid", pl.get("run_id")):
            break
    rid, filtered = rid or _NIL_UUID, list[tuple[int, JsonObject]]()
    for ev in events:
        s, sid = ev.get("stream_seq", ev.get("seq")), _tok("uuid", ev.get("stream_id"))
        ok_s = isinstance(s, int) and not isinstance(s, bool) and after_seq < s <= through_seq
        if ev.get("stream_kind") in (None, "run") and sid in (None, rid) and ok_s:
            filtered.append((cast("int", s), ev))
    filtered.sort(key=lambda x: x[0])
    if through_seq == 0:
        return _kv(_PAGE_K, (rid, 0, BUILDER_VERSION, 0, [], None, "complete"))
    cursor_fn: Callable[[int], str] = encode_cursor or (lambda sv: f"v1:{rid}:{through_seq}:{sv}")
    entries, page_seen, total_nodes, total_edges, entries_b = list[JsonObject](), set[_Pair](), 0, 0, 0
    page_cov, stopped_early, expected_seq = "complete", False, after_seq + 1
    af, xf = authorized_foreign_ids or frozenset(), explicit_foreign_ids or frozenset()
    for seq, ev in filtered:
        if len(entries) >= min(limit, MAX_PAGE_EVENTS):
            stopped_early = True
            break
        entry, eloc, eb = _project_event(rid, seq, ev, (page_seen, known_local_ids, af, xf))
        nn, ne = len(_as_seq(entry.get("nodes")) or ()), len(_as_seq(entry.get("edges")) or ())
        sh_b = _cbytes(_kv(_PAGE_K, (rid, through_seq, 1, seq, [], cursor_fn(seq), "unavailable")))
        over = total_nodes + nn > MAX_PAGE_NODES or total_edges + ne > MAX_PAGE_EDGES
        if over or sh_b + entries_b + eb + len(entries) > MAX_PAGE_BYTES:
            if entries:
                stopped_early = True
                break
            entry, nn, ne, eloc = _unrep(entry, "PAYLOAD_UNREPRESENTABLE"), 0, 0, set[_Pair]()
            eb = _cbytes(entry)
        if seq != expected_seq:
            page_cov = _cmax(page_cov, "partial")
        expected_seq = seq + 1
        entries.append(entry)
        page_seen.update(eloc)
        total_nodes, total_edges, entries_b = total_nodes + nn, total_edges + ne, entries_b + eb
        page_cov = _cmax(page_cov, str(entry["coverage"]))
    last_s = int(cast("int", entries[-1]["seq"])) if entries else after_seq
    stopped_early |= len(filtered) >= min(limit, MAX_PAGE_EVENTS) and last_s < through_seq
    scanned = last_s if stopped_early else through_seq
    next_after = cursor_fn(scanned) if (stopped_early and scanned < through_seq) else None
    if not stopped_early and last_s < through_seq:
        page_cov = "unavailable" if not entries else _cmax(page_cov, "partial")
    return _kv(_PAGE_K, (rid, through_seq, BUILDER_VERSION, scanned, list(entries), next_after, page_cov))
