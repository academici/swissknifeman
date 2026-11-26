"""Phase-A control-plane context assembly; host reads remain declarative requests."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.kernel.data_classification import HOST_PRIVATE
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import EntityId, ResourceVersionId, ScopeId
from skm.kernel.tokens import TokenEstimator
from skm.modules.access import public as access
from skm.modules.artifacts import public as artifacts
from skm.modules.context.application._skills import emit_skills
from skm.modules.context.domain.blocks import BlockType, BudgetClass, TrustLevel, canonical_json_digest
from skm.modules.context.domain.draft import (
    ContextDraft,
    make_repo_instruction_requests,
    make_repo_path_request,
    make_research_request,
)
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.domain.manifest import DraftAssembler
from skm.modules.context.domain.payload_compiler import PayloadCompiler
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason
from skm.modules.context.domain.render import (
    EntityPromptScope,
    build_prompt_variables,
    emit_execution_state_blocks,
    fence,
    fence_tag_for_path,
    render_task_contract_markdown,
    substitute,
)
from skm.modules.context.domain.request import ContextRequest, validate_owner_ref, validate_request_envelope
from skm.modules.context.generated.settings import ContextRepoInstructionsMode, ContextSettings
from skm.modules.context.ports import ContextRepository, MemoryRetriever, TextStore
from skm.modules.extensions import public as extensions
from skm.modules.planning import public as planning
from skm.modules.workspace import public as workspace
from skm.platform.jsonc.canonical import canonical_bytes
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.actor import Actor
    from skm.kernel.gateways import Gateways
    from skm.kernel.ids import ContextManifestId
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork
    from skm.platform.config import EffectiveConfig

__all__ = ["assemble_draft"]
_CHECK_FIELDS = {"check_key", "exit_code", "tail", "tail_bytes", "full_log_file_version_id"}
_LOG_CLIP = re.compile(r"… \[clipped [0-9 ]+ bytes(?:; full: file_version:[0-9a-f-]+)?\]")

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)
_DEFAULT_WRAPPER = "## {{ block.title }}\n\n{{ block.content }}"
_CLS_RANK: Mapping[str, int] = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
_REPO_RANK: Mapping[str, int] = {"none": 0, "constraints": 1, "full": 2}
_STAGE_FOR_ROLE: Mapping[str, planning.MaterialStage] = {
    **dict.fromkeys(("executor", "scout", "researcher"), planning.MaterialStage.EXECUTION),
    **dict.fromkeys(("triager", "reviewer", "advisor"), planning.MaterialStage.REVIEW),
    "registrar": planning.MaterialStage.ACCEPTANCE,
}
_VALID_BLOCK_VALUES = frozenset(bt.value for bt in BlockType)


def _extract_entity_scope(
    spec: planning.Specification, entity_id: EntityId | None, plan_title: str
) -> EntityPromptScope:
    forb = [f"{r.mount}:{r.pattern}" for r in spec.execution_constraints.forbidden_paths]
    if entity_id is None:
        return EntityPromptScope(
            key="plan_audit",
            title=plan_title,
            goal=spec.goal or "Audit the published plan specification.",
            why="(none)",
            work_kind="review",
            instructions="Audit plan completeness, dependencies, acceptance criteria, and readiness.",
            guidance=spec.context_md or "(none)",
            write_paths=(),
            forbidden_paths=tuple(dict.fromkeys(forb)),
            deliverables=(),
            outputs=(),
            rules=spec.rules,
            chain_keys=frozenset(),
        )
    ent = spec.entity(entity_id)
    key = spec.display_key(ent)
    ancestors = spec.ancestors(entity_id)
    writes: list[str] = []
    deliverables: list[str] = []
    rules: list[str] = list(spec.rules)
    guidance_parts: list[str] = []
    for node in (ent, *ancestors):
        writes.extend(
            f"{getattr(e, 'mount', 'repo')}:{getattr(e, 'pattern', '')}"
            for e in getattr(node, "write_scope", ())
        )
        if sc := getattr(node, "scope", None):
            if node is ent or not writes:
                writes.extend(f"repo:{p}" for p in getattr(sc, "include", ()))
            forb.extend(f"repo:{p}" for p in getattr(sc, "exclude", ()))
        deliverables.extend(str(d) for d in getattr(node, "deliverables", ()))
        rules.extend(str(r) for r in getattr(node, "rules", ()))
        if g_md := getattr(node, "guidance_md", None):
            guidance_parts.append(str(g_md))
    outputs = [f"{getattr(o, 'mount', 'repo')}:{getattr(o, 'path', '')}" for o in getattr(ent, "outputs", ())]
    outputs.extend(
        f"{getattr(a, 'mount', 'repo')}:{getattr(a, 'path', '')}"
        for a in getattr(ent, "artifacts", ())
        if getattr(a, "role", "") == "output"
    )
    wk_raw = getattr(ent, "work_kind", None) or next(
        (getattr(a, "work_kind", None) for a in ancestors if getattr(a, "work_kind", None) is not None), None
    )
    title = str(getattr(ent, "title", key))
    goal = str(getattr(ent, "goal", None) or getattr(ent, "summary", None) or spec.goal or title)
    return EntityPromptScope(
        key=key,
        title=title,
        goal=goal,
        why=str(getattr(ent, "why", None) or "(none)"),
        work_kind=str(getattr(wk_raw, "value", wk_raw) or "code"),
        instructions=str(getattr(ent, "instructions_md", None) or getattr(ent, "summary", None) or goal),
        guidance="\n\n".join(guidance_parts) if guidance_parts else "(none)",
        write_paths=tuple(dict.fromkeys(writes)),
        forbidden_paths=tuple(dict.fromkeys(forb)),
        deliverables=tuple(dict.fromkeys(deliverables)),
        outputs=tuple(dict.fromkeys(outputs)),
        rules=tuple(dict.fromkeys(rules)),
        chain_keys=frozenset({key, *(spec.display_key(a) for a in ancestors)}),
    )


def _load_templates(
    uow: UnitOfWork,
    profile: extensions.AgentProfile,
    *,
    config: EffectiveConfig,
    pins: extensions.PackPins | None,
) -> tuple[dict[str, str], dict[BlockType, tuple[str, ...]], dict[str, tuple[str, str, TrustLevel]]]:
    known = extensions.known_keys(uow, extensions.ResourceKind.PROMPT_BLOCK, config=config, pins=pins)
    templates: dict[str, str] = {"shared/block_wrapper": _DEFAULT_WRAPPER}
    prompt_plan: dict[BlockType, tuple[str, ...]] = {}
    group_prov: dict[str, tuple[str, str, TrustLevel]] = {}

    def _fetch(rkey: str) -> tuple[str, str, TrustLevel]:
        view = extensions.resolve_resource(
            uow, extensions.ResourceKind.PROMPT_BLOCK, rkey, config=config, pins=pins
        )
        templates[rkey] = extensions.load_text_resource(uow, ResourceVersionId(view.resource_version_id))[1]
        return f"resource:{view.kind.value}:{view.key}@{view.version}", view.digest, TrustLevel.SYSTEM

    for extra_key in ("shared/block_wrapper", "shared/work_policy"):
        if extra_key in known:
            _fetch(extra_key)
    for grp_name, rkeys in profile.prompt.blocks.items():
        if not rkeys:
            continue
        refs, vers, _ = zip(*(_fetch(rk) for rk in rkeys), strict=True)
        group_prov[grp_name] = (",".join(refs), ",".join(vers), TrustLevel.SYSTEM)
        if grp_name in _VALID_BLOCK_VALUES:
            prompt_plan[BlockType(grp_name)] = tuple(rkeys)
    return templates, prompt_plan, group_prov


def _emit_supporting(  # noqa: PLR0912, PLR0913 -- shared inputs for supporting blocks
    b: DraftAssembler,
    uow: UnitOfWork,
    gateways: Gateways,
    spec: planning.Specification | None,
    profile: extensions.AgentProfile,
    req: ContextRequest,
    settings: ContextSettings,
    escope: EntityPromptScope,
    actor: Actor | None,
    config: EffectiveConfig,
) -> None:
    emit_skills(b, uow, spec, profile, req, settings, config=config)
    stage = _STAGE_FOR_ROLE.get(req.purpose.role, planning.MaterialStage.EXECUTION)
    inc_opt = bool(profile.context.get("include_optional_materials", True))
    max_cls = _CLS_RANK[settings.max_classification_for_runtime.value]
    fmax = settings.host_inputs.file_max_bytes
    for mat in spec.materials if spec is not None else ():
        if not (mat.is_global or not escope.chain_keys or bool(set(mat.applies_to) & escope.chain_keys)):
            continue
        is_req = stage in mat.required_for
        if not is_req and not inc_opt:
            mat_sk = "external" if mat.kind is planning.MaterialKind.EXTERNAL_SOURCE else mat.kind.value
            b.exclude(BlockType.MATERIALS, mat_sk, f"material:{mat.key}", ExcludeReason.OPTIONAL_DISABLED)
        elif mat.kind is planning.MaterialKind.FILE_VERSION and mat.file_version_id is not None:
            fref = f"file_version:{mat.file_version_id}"
            try:
                fv = artifacts.require_ready_versions(uow, req.workspace_id, (mat.file_version_id,))[0]
            except PreconditionFailed as exc:
                if is_req:
                    raise PreconditionFailed(
                        ErrorCode.CONTEXT_MATERIAL_UNAVAILABLE,
                        f"required material {mat.key} is unavailable",
                        details={"material": mat.key, "reason": ExcludeReason.FILE_VERSION_NOT_READY.value},
                    ) from exc
                b.exclude(BlockType.MATERIALS, "file_version", fref, ExcludeReason.FILE_VERSION_NOT_READY)
                continue
            cls_str = str(getattr(fv, "classification", "internal"))
            if _CLS_RANK.get(cls_str, 1) > max_cls:
                if is_req:
                    raise PreconditionFailed(
                        ErrorCode.CONTEXT_MATERIAL_UNAVAILABLE,
                        f"required material {mat.key} exceeds max_classification_for_runtime",
                        details={"material": mat.key, "reason": ExcludeReason.CLASSIFICATION_FORBIDDEN.value},
                    )
                reason = ExcludeReason.CLASSIFICATION_FORBIDDEN
                b.exclude(BlockType.MATERIALS, "file_version", fref, reason, source_version=fv.digest)
                continue
            txt = artifacts.read_text_content(uow, mat.file_version_id, max_bytes=fmax)
            if txt is None:
                body = (
                    f"Binary file materialized at `.skm/materials/{mat.file_version_id}/"
                    f"{fv.original_filename}`."
                )
                rsn = IncludeReason.BINARY_REFERENCE
            else:
                tag = fence_tag_for_path(fv.original_filename)
                body = fence(txt, tag) if tag else txt
                rsn = IncludeReason.REQUIRED_MATERIAL if is_req else IncludeReason.OPTIONAL_MATERIAL
            b.add(
                BlockType.MATERIALS,
                f"Material: {mat.title}",
                body,
                "file_version",
                fref,
                source_version=fv.digest,
                trust=TrustLevel.PROJECT,
                reason=rsn,
            )
        elif mat.kind is planning.MaterialKind.REPOSITORY_PATH and mat.path is not None:
            b.host_inputs.append(
                make_repo_path_request(
                    b.next_hi(), mount=mat.mount or "repo", path=mat.path, max_bytes=fmax, required=is_req
                )
            )
        elif mat.kind is planning.MaterialKind.EXTERNAL_SOURCE:
            body = f"URL: {mat.url or '(none)'} (content not fetched on control plane)."
            b.add(
                BlockType.MATERIALS,
                f"External Reference: {mat.title}",
                body,
                "external",
                f"external:{mat.url or mat.key}",
                source_version=mat.content_digest,
                trust=TrustLevel.EXTERNAL,
                reason=IncludeReason.EXTERNAL_REFERENCE,
            )
    repo_rank = min(
        _REPO_RANK[settings.repo_instructions.mode.value],
        _REPO_RANK.get(str(profile.context.get("repo_instructions", "full")), 2),
    )
    if repo_rank > 0 and settings.repo_instructions.max_files > 0 and settings.repo_instructions.files:
        secs = tuple(
            str(s) for s in cast("Sequence[object]", profile.context.get("repo_instruction_sections", ()))
        )
        reqs = make_repo_instruction_requests(
            b.hi_index,
            write_paths=escope.write_paths,
            max_files=settings.repo_instructions.max_files,
            files=settings.repo_instructions.files,
            max_bytes=settings.repo_instructions.max_bytes,
            constraints_only=(repo_rank == _REPO_RANK[ContextRepoInstructionsMode.CONSTRAINTS.value]),
            sections=secs,
            self_loaded_files=req.runtime.self_loaded_instruction_files,
        )
        b.host_inputs.extend(reqs)
        b.hi_index += len(reqs)
    for rq in req.research_queries:
        b.host_inputs.append(
            make_research_request(
                b.next_hi(),
                query_spec=rq,
                query_digest=sha256_text(rq.text),
                max_bytes=settings.host_inputs.max_bytes,
            )
        )
    pm = profile.context.get("memory_top_k", 0)
    mk = min(settings.memory.top_k, int(pm) if isinstance(pm, int) and not isinstance(pm, bool) else 0)
    if actor is not None and settings.memory.enabled and mk > 0 and gateways.has(MemoryRetriever):
        hits = gateways.get(MemoryRetriever).search(
            uow,
            actor=actor,
            workspace_id=req.workspace_id,
            project_id=req.project_id,
            query=f"{escope.title}\n{escope.goal}",
            top_k=mk,
        )
        for idx, hit in enumerate(hits):
            if hit.get("classification") == HOST_PRIVATE:
                continue
            if htxt := str(hit.get("text", "")).strip():
                sver = None if hit.get("source_version") is None else str(hit["source_version"])
                agrp = None if hit.get("atomic_group") is None else str(hit["atomic_group"])
                b.add(
                    BlockType.MEMORY,
                    "Project Memory",
                    htxt,
                    "memory",
                    str(hit.get("source_ref", f"memory:hit:{idx}")),
                    source_version=sver,
                    trust=TrustLevel.MEMORY,
                    reason=IncludeReason.MEMORY_MATCH,
                    atomic_group=agrp,
                )


def _review_feedback(request: ContextRequest, config: EffectiveConfig) -> ContextRequest:
    feedback = request.execution_blocks.review_feedback
    if feedback is None or "fix_brief" not in feedback:
        return replace(request, execution_blocks=replace(request.execution_blocks, review_feedback=None))

    try:
        doc: Any = deepcopy(feedback["fix_brief"])
        SchemaRegistry.load_default().require_valid("urn:skm:execution:fix-brief:v1", doc)
        caps, items, checks = doc["limits"], doc["items"], doc["checks"]
        fields = {"problem": 1200, "fix": 800, "observed": 600, "reproduction": 400}
        valid = (doc["source_review_id"] is None) != (doc["source_check_round"] is None)
        valid = valid and type(doc["truncated"]) is bool
        valid = valid and all(caps[k] <= cast("int", config.get(f"execution.handoff.{k}")) for k in caps)
        keys = [it["finding_key"] for it in items]
        ranks = [("blocker", "major", "minor", "nit").index(it["severity"]) for it in items]
        valid = valid and ranks == sorted(ranks) and len(set(keys)) == len(keys)
        valid = valid and not set(keys).intersection(doc["deferred_finding_keys"])
        for item in items:
            valid = valid and all(len(item[k]) <= n for k, n in fields.items())
            valid = valid and sum(len(item[k]) for k in fields) <= caps["max_finding_chars"]
        for check in checks:
            valid = valid and set(check) == _CHECK_FIELDS
            valid = valid and isinstance(check["check_key"], str) and type(check["tail_bytes"]) is int
            valid = valid and (check["exit_code"] is None or type(check["exit_code"]) is int)
            lines = check["tail"].splitlines()
            valid = valid and len(lines) <= 40 + bool(lines and _LOG_CLIP.fullmatch(lines[0]))
            valid = valid and len(check["tail"].encode("utf-8")) == check["tail_bytes"]
            valid = valid and check["tail_bytes"] <= caps["max_inline_evidence_bytes"]
            if check["full_log_file_version_id"] is not None:
                UUID(check["full_log_file_version_id"])
        blockers = sum(it["severity"] == "blocker" for it in items)
        valid = valid and len(items) <= max(caps["max_findings"], blockers)
        valid = valid and (
            len(canonical_bytes(doc)) <= caps["max_total_bytes"]
            or (
                len(items) == blockers
                and len(canonical_bytes({**doc, "items": []})) <= caps["max_total_bytes"]
            )
        )
        valid = valid and all(isinstance(k, str) for k in doc["deferred_finding_keys"])
        cut = bool(doc["deferred_finding_keys"] or any("[clipped " in str(i) for i in (*items, *checks)))
        valid = valid and (not cut or doc["truncated"] is True)
        body = {k: v for k, v in doc.items() if k != "digest"}
        valid = valid and doc["digest"] == canonical_json_digest(body)
        if not valid:
            raise ValueError("invalid fix brief")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid review feedback fix brief") from exc
    clean: JsonObject = {"fix_brief": doc, "full_report_file_version_id": doc["full_report_file_version_id"]}
    return replace(request, execution_blocks=replace(request.execution_blocks, review_feedback=clean))


def assemble_draft(  # noqa: PLR0912, PLR0915 -- sequential 6-stage ladder assembly
    uow: UnitOfWork,
    gateways: Gateways,
    request: ContextRequest,
    *,
    config: EffectiveConfig,
    owner_ref: str,
    actor: Actor | None = None,
    manifest_id: ContextManifestId | None = None,
    inline_task: tuple[str, str] | None = None,
) -> ContextDraft:
    request = _review_feedback(request, config)
    compiler = PayloadCompiler(request.runtime.forbidden_params, request.runtime.legacy_prompt_phrases)
    compiler.validate_parameters(request.runtime.parameters, request.runtime.incompatible_param_groups)
    wp = validate_request_envelope(request, owner_ref, adhoc=inline_task is not None)
    owner = validate_owner_ref(owner_ref, request.purpose.step_ref)
    if owner is not None:
        if (
            actor is None
            or actor.principal_id != owner
            or "context.assemble" not in access.effective_permissions(uow, actor, ScopeId(request.project_id))
        ):
            raise Forbidden(
                ErrorCode.FORBIDDEN, "standalone context assembly requires the project permission and owner"
            )
        if manifest_id is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "standalone assembly requires a manifest id")
        if workspace.get_project(uow, request.project_id).workspace_id != request.workspace_id:
            raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "project scope mismatch")
    settings = config.section(ContextSettings)
    est_id = "heuristic-v1" if settings.token_estimator == "heuristic" else settings.token_estimator
    estimator = gateways.get(TokenEstimator)
    if estimator.estimator_id != est_id:
        raise PreconditionFailed(
            ErrorCode.EXTENSION_INCOMPATIBLE,
            f"configured token_estimator {est_id!r} does not match gateway {estimator.estimator_id!r}",
            details={"expected": est_id, "actual": estimator.estimator_id},
        )
    profile = extensions.load_agent_profile(uow, request.agent_profile_version_id)
    if profile.role != request.purpose.role:
        raise PreconditionFailed(
            ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH,
            f"profile {profile.key} is declared for role {profile.role!r}, expected {request.purpose.role!r}",
            details={"key": profile.key, "role": profile.role, "expected": request.purpose.role},
        )
    plan_ref = planning.get_plan_ref(uow, request.plan_id) if request.plan_id is not None else None
    if plan_ref is not None and (plan_ref.workspace_id, plan_ref.project_id) != (
        request.workspace_id,
        request.project_id,
    ):
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "plan scope mismatch")
    rev_meta = (
        planning.get_revision_meta(uow, request.revision_id) if request.revision_id is not None else None
    )
    if rev_meta is not None and (rev_meta.workspace_id, rev_meta.project_id, rev_meta.plan_id) != (
        request.workspace_id,
        request.project_id,
        request.plan_id,
    ):
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "revision scope mismatch")
    spec = planning.get_revision_specification(uow, rev_meta.revision_id) if rev_meta is not None else None
    plan_title = plan_ref.title if plan_ref is not None else request.project_slug
    revision_digest = rev_meta.digest if rev_meta is not None else None
    project_context = owner is not None and request.entity_id is None
    if project_context or inline_task is not None:
        instructions, work_kind = inline_task or ("Use the supplied project context.", "research")
        escope = EntityPromptScope(
            key="standalone" if project_context else "ADHOC-1",
            title=plan_title,
            goal=(spec.goal if spec is not None else "Assemble project context.")
            if project_context
            else "Complete the supplied task.",
            why="(none)",
            work_kind=work_kind,
            instructions=instructions,
            guidance=(spec.context_md if spec is not None else None) or "(none)",
            write_paths=(),
            forbidden_paths=(),
            deliverables=(),
            outputs=(),
            rules=spec.rules if spec is not None else (),
            chain_keys=frozenset(),
        )
    elif spec is not None:
        escope = _extract_entity_scope(spec, request.entity_id, plan_title)
    else:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "task context requires a published revision")
    escope = replace(
        escope,
        instructions=compiler.clean_prompt(escope.instructions),
        guidance=compiler.clean_prompt(escope.guidance),
    )
    templates, prompt_plan, prov = _load_templates(
        uow, profile, config=config, pins=cast("extensions.PackPins | None", request.pack_pins)
    )
    templates = {key: compiler.clean_prompt(body) for key, body in templates.items()}
    notes_templates = prompt_plan.pop(BlockType.RUNTIME_NOTES, ())
    for req_grp in ("system_constraints", "role_contract", "result_contract"):
        if req_grp not in prov:
            raise PreconditionFailed(
                ErrorCode.EXTENSION_INCOMPATIBLE,
                f"missing prompt group {req_grp!r}",
                details={"group": req_grp},
            )
    out_lang = request.run.output_language or settings.output_language or "en"
    merged_rules = tuple(
        dict.fromkeys(
            clean
            for rule in (*request.run.rules_extra, *settings.rules.extra)
            if (clean := compiler.clean_prompt(rule))
        )
    )
    variables = build_prompt_variables(
        request,
        escope,
        plan_alias=plan_ref.alias if plan_ref is not None else "",
        plan_title=plan_title,
        plan_goal=spec.goal if spec is not None else "",
        revision_no=rev_meta.revision_no if rev_meta is not None else None,
        profile_key=profile.key,
        result_schema=profile.result_schema,
        wp=wp,
        output_lang=out_lang,
        rules_extra=merged_rules,
    )
    pmax = profile.context.get("max_total_tokens")
    pcap = int(pmax) if isinstance(pmax, int) and not isinstance(pmax, bool) else settings.max_total_tokens
    win_cap = max(1000, int(request.runtime.context_window_tokens * settings.window_fraction))
    total_limit = max(1000, min(settings.max_total_tokens, pcap, win_cap))
    b = DraftAssembler(estimator, settings.block.max_tokens, templates, prompt_plan, variables)

    def _sub_group(grp: str) -> str:
        keys = profile.prompt.blocks.get(grp, ())
        return "\n\n".join(substitute(templates[k], variables).strip() for k in keys)

    if request.resume is not None:
        rbody = (
            f"## Resumed session\n\nResuming `{request.resume.session_ref}` "
            f"(round {request.purpose.round_no})."
        )
        if "resume_note" in prov:
            rbody = _sub_group("resume_note")
        b.add(
            BlockType.RESUME_NOTE,
            "",
            rbody,
            "core",
            f"resume:{request.resume.session_ref}",
            source_version=request.resume.previous_task_digest,
        )
    for btype, grp in (
        (BlockType.SYSTEM_CONSTRAINTS, "system_constraints"),
        (BlockType.ROLE_CONTRACT, "role_contract"),
    ):
        gref, gver, gtr = prov[grp]
        b.add(btype, "", _sub_group(grp), "resource", gref, source_version=gver, trust=gtr)
    rr_base = (
        f"## Run rules\n\nWorkflow: `{request.run.workflow_key}`. "
        f"Attempt `{request.purpose.attempt_no}`, round `{request.purpose.round_no}`. "
        f"Verification intensity: `{wp.verification_intensity}`."
    )
    if "run_rules" in prov:
        rr_base = _sub_group("run_rules")
    rr_extra = "\n".join(f"- {r}" for r in merged_rules)
    rr_ref, rr_ver, rr_tr = prov.get("run_rules", ("core:run_rules", revision_digest, TrustLevel.SYSTEM))
    b.add(
        BlockType.RUN_RULES,
        "",
        f"{rr_base}\n\n{rr_extra}" if rr_extra else rr_base,
        "resource" if "run_rules" in prov else "core",
        rr_ref,
        source_version=rr_ver,
        trust=rr_tr,
    )
    compiler.emit_runtime_notes(
        b, runtime_id=request.runtime.runtime_id, notes=request.runtime.notes, template_keys=notes_templates
    )
    b.add(
        BlockType.TASK_CONTRACT,
        "",
        render_task_contract_markdown(escope, wp, templates, prompt_plan, variables),
        "core" if project_context else "spec",
        "core:standalone" if project_context else f"spec:{request.revision_id}/{escope.key}#task_contract",
        source_version=sha256_text(f"{revision_digest}:{wp.digest}"),
    )
    if project_context:
        acc_lines = ["- Apply the selected project and role constraints."]
    elif request.entity_id is None:
        acc_lines = ["- Audit all plan entities, dependencies, acceptance criteria, and readiness."]
    else:
        acc_lines = [
            f"- Criterion [{c.key}] ({c.verification_mode.value}): {c.statement}"
            for c in (spec.criteria if spec is not None else ())
            if c.owner in escope.chain_keys
        ]
        acc_lines.extend(
            f"- Check [{ck.key}] ({ck.kind.value}, required={ck.required}): {ck.title}"
            for ck in (spec.checks if spec is not None else ())
            if ck.owner in escope.chain_keys
        )
        if not acc_lines:
            acc_lines.append("- Satisfy the target contract and pass all applicable checks.")
    acc_txt = "## Acceptance criteria\n\n" + "\n".join(acc_lines)
    if "acceptance" in prov:
        acc_txt = f"{acc_txt}\n\n{_sub_group('acceptance')}"
    b.add(
        BlockType.ACCEPTANCE,
        "",
        acc_txt,
        "core" if project_context else "spec",
        "core:standalone#acceptance"
        if project_context
        else f"spec:{request.revision_id}/{escope.key}#acceptance",
        source_version=revision_digest,
    )
    req_lines = [
        f"- [{r.key}] ({r.priority.value}): {r.statement}"
        for r in (spec.requirements if spec is not None else ())
        if request.entity_id is not None
        and (not getattr(r, "applies_to", ()) or bool(set(getattr(r, "applies_to", ())) & escope.chain_keys))
    ]
    dec_lines = [
        f"- [{d.key}] {d.title}: {getattr(d, 'chosen', '') or getattr(d, 'summary', '')}"
        for d in (spec.decisions if spec is not None else ())
        if not escope.chain_keys or bool(set(getattr(d, "applies_to", ())) & escope.chain_keys)
    ]
    add_plan = partial(b.add, source_version=revision_digest, reason=IncludeReason.EXPLICIT_PLAN)
    for btype, title, lines in (
        (BlockType.REQUIREMENTS, "Requirements", req_lines),
        (BlockType.DECISIONS, "Design Decisions", dec_lines),
    ):
        if lines:
            ref = f"spec:{request.revision_id}/{escope.key}#{btype.value}"
            add_plan(btype, title, "\n".join(lines), "spec", ref)
    cand_diff = (
        artifacts.read_text_content(
            uow,
            request.execution_blocks.candidate.diff_file_version_id,
            max_bytes=settings.host_inputs.file_max_bytes,
        )
        if request.execution_blocks.candidate is not None
        else None
    )
    ph = profile.context.get("history_max_steps", settings.history.max_steps)
    hcap = min(settings.history.max_steps, int(ph) if isinstance(ph, int) and not isinstance(ph, bool) else 0)
    emit_execution_state_blocks(b, request, cand_diff, history_cap=hcap)
    _emit_supporting(b, uow, gateways, spec, profile, request, settings, escope, actor, config)
    res_ref, res_ver, res_tr = prov["result_contract"]
    b.add(
        BlockType.RESULT_CONTRACT,
        "",
        _sub_group("result_contract"),
        "resource",
        res_ref,
        source_version=res_ver,
        trust=res_tr,
    )
    received = getattr(getattr(uow, "_meta", None), "received_at", None)
    now = received if isinstance(received, datetime) and received.tzinfo is not None else _EPOCH_UTC
    draft, manifest, texts = b.build(
        request,
        total_limit=total_limit,
        class_limits={
            BudgetClass.CORE: settings.budget.core,
            BudgetClass.TASK: None,
            BudgetClass.SUPPORTING: settings.budget.supporting,
            BudgetClass.RETRIEVAL: settings.budget.retrieval,
        },
        skills_budget=settings.skills.budget_tokens,
        repo_max_files=settings.repo_instructions.max_files,
        owner_ref=owner_ref,
        created_at=now,
        manifest_id=manifest_id,
    )
    snapshot = {
        "templates": dict(draft.templates),
        "prompt_plan": {bt.value: list(keys) for bt, keys in draft.prompt_plan.items()},
        "variables": dict(draft.variables),
        "titles": {f"d:{b.ordinal}": b.title for b in draft.blocks}
        | {f"c:{c.block.ordinal}": c.block.title for c in draft.conditional},
        "store_host_content": settings.store_host_block_content,
    }
    manifest = replace(manifest, route={**manifest.route, "render_snapshot": snapshot})
    uow.repo(TextStore).put_many(texts)
    uow.repo(ContextRepository).add_draft(manifest)
    return draft
