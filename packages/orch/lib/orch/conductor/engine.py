"""The conductor loop: claim, brief, prepare, then the stages of one piece of work, registration and the commit.

Every step of a piece of work has a key (``brief``, ``prepare``, ``scout``, ``executor.1``, ``checks.1``,
``review.1``, ``triage.1``, ``register``, ``commit``) and is recorded in ``state.json`` before work starts and when it closes.
``resume`` reconciles interrupted steps and runs the same loop again: a closed step returns its recorded result, so the loop takes
the same path up to the step that did not close. The work source is reached only through ``orch.py source``; the
roles only through the launch catalog (or ``[orch.conductor.argv]``) and see the execution-input, never the plan.

The conductor stops only on: a blocked piece of work (``on_blocked = "stop"``), red checks or confirmed findings
whose corrections stopped making progress (or reached the ceiling of their limit), a route below the minimum of the
work, an unavailable provider or role, a refusal of the work source, or a dirty working tree before new work.
Most time and token limits print beacons; explicit hard token limits stop new model calls at the boundary of
accounted usage, preserving closed steps for resume.

The code lives by layer (knowledge/p11-refactor#extract): ``domain`` (the piece, the stop, the rules of a report),
``infrastructure`` (run files and clocks, role processes, the work source), ``policies`` (routes, limits, retries,
the sandbox, risk, budgets), ``stages`` (scout to registration) and ``application`` (the verbs and the loop). This
module is the facade: :class:`Conductor` keeps the run (its options, state and files) and binds the functions of the
layers as its methods; the public names stay importable from here.
"""
from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional

from orch import catalog as catalogs, sandbox
from orch.conductor import process
from orch.conductor.application import budget_service, limits_service, loop, recovery, retry_service, review_plan
from orch.conductor.application import route_service, run_service
from orch.conductor.domain import report as report_rules, route as route_rules
from orch.conductor.domain.item import Item
from orch.conductor.domain.report import continued, evidence_paths, findings_problems, report_problems
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import beacon_events, launch_plan, results, roles, sessions, tree, usage
from orch.conductor.infrastructure import work_source
from orch.conductor.infrastructure.heartbeat import Heartbeat
from orch.conductor.infrastructure.clock import new_run_id, sleep, unit_random, utc_now, utc_stamp, wall
from orch.conductor.infrastructure.files import (OPTIONS_COPY, REPORTS, RUN_FILE, STATE_FILE, RunStore, read_json,
                                                 runs_root, safe, write_json)
from orch.conductor.infrastructure.work_source import FALLBACK_ARTIFACTS
from orch.conductor.policies import allowance, retry_policy
from orch.conductor.policies import risk as risk_policy, sandbox as sandbox_policy
from orch.conductor.policies.allowance import BATCH_FIELDS, BATCH_LIMITS
from orch.conductor.policies.routing import CLASS_RANK, EFFORT_RANK, LAUNCH_ROLE
from orch.conductor import stubs as stubs_mod
from orch.conductor.progress import Progress
from orch.conductor.stages import advice, checks_stage, close, context, correction, execute, finish
from orch.conductor.stages import research as research_stage, review as review_stage, scout as scout_stage
from orch.conductor.stages import step as step_stage, triage as triage_stage
from orch.settings import ORCH_ROOT

# The names other modules and the tests import from here. ``process`` and ``sandbox`` are the modules the tests patch
# (``process.available``, ``process.run_role``, ``sandbox.probe``); the clocks are patched in ``infrastructure.clock``.
__all__ = ["BATCH_FIELDS", "BATCH_LIMITS", "CLASS_RANK", "Conductor", "EFFORT_RANK", "FALLBACK_ARTIFACTS", "Item",
           "LAUNCH_ROLE", "OPTIONS_COPY", "ORCH_ROOT", "REPORTS", "RUN_FILE", "RunStore", "STATE_FILE", "STATUS_EXIT", "Stop",
           "continued", "evidence_paths", "findings_problems", "new_run_id", "process", "read_json", "report_problems",
           "runs_root", "safe", "sandbox", "sleep", "unit_random", "utc_now", "utc_stamp", "wall", "write_json"]

STATUS_EXIT = {"finished": 0, "stopped": 1, "waiting": 4}


class Conductor:
    """One conductor run in a project (a git repository): it keeps the run (options, state, files, the agent run of each
    thread); every step is a function of a layer bound below as a method, so a step calls the others through ``self``."""

    def __init__(self, *, project: Path, settings, config_file: Optional[Path] = None, mode: str = "text",
                 stream=None, model_catalog: Optional[Path] = None, roles_dir: Optional[Path] = None,
                 env: Optional[dict] = None, clock: Optional[Callable[[], str]] = None,
                 project_resolution: Optional[str] = None):
        self.project = Path(project).resolve()
        self.project_resolution = project_resolution
        self.settings = settings
        self.config_file = Path(config_file).resolve() if config_file else None
        self.mode = mode
        self.stream = stream
        self.model_catalog = model_catalog
        self.roles_dir = roles_dir
        self.env = env
        self.clock = clock
        self.conductor = dict(settings.conductor or {})
        self._catalog = None
        self._step_tokens = {"input": 0, "output": 0}  # unbound calls; a logical step uses its own slot
        self._stage_slots = {}  # (item, step) -> the durable fresh-token bucket of that logical step
        self._local = threading.local()  # the agent run of the role this thread runs: usage and children belong to it
        self.run_id = ""
        self.directory = Path()
        self.store: Optional[RunStore] = None
        self.run_doc: dict = {}
        self.state: dict = {}
        self.progress: Optional[Progress] = None
        self.heartbeat: Optional[Heartbeat] = None
        self.instructions: dict = {}  # the stubs snapshot of the run (``instructions.json``)
        self._instructions_lock = threading.Lock()

    _current_step: Optional[str] = None  # the step that runs now, for the RUN_SLOW beacon

    # ------------------------------------------------------------------ run files

    def _open(self, run_id: str, run_doc: dict, state: dict, store: Optional[RunStore] = None) -> None:
        self.run_id, self.run_doc, self.state = run_id, run_doc, state
        self.store = store or RunStore(self.project, run_id)
        self.directory = self.store.directory
        self.heartbeat = Heartbeat(self.directory, run_id, on_failure=self._heartbeat_failed)
        self.progress = Progress(run_id, self.directory, self.mode, self.stream, self.clock, observer=self.heartbeat.observe)
        self.instructions = read_json(self.directory / stubs_mod.SNAPSHOT_FILE) or {}

    def _heartbeat_failed(self, error: OSError) -> None:
        """heartbeat.json could not be written: said once per run; the run goes on without it."""
        self.progress.emit("info", reason_code="HEARTBEAT_NOT_WRITTEN",
                           message=f"heartbeat.json was not written ({error}); the run goes on without it")

    def _stub(self, role: str, route: Optional[dict] = None) -> tuple:
        """``(origin, text)`` of the additional instructions of ``role`` from the snapshot of the run."""
        provider, family = None, None
        has_variants = any("variant" in part for found in self.instructions.get("targets", {}).values()
                           for part in found.get("parts", []))
        if route is not None and role in stubs_mod.ROLES and has_variants:
            provider, model = route["provider"], route["model"]
            key = f"{provider}/{model}"
            with self._instructions_lock:
                resolved = self.instructions.setdefault("variant_resolution", {})
                if key not in resolved:
                    resolved[key] = stubs_mod.model_family(provider, model, self._catalog_get().models)
                    write_json(self.directory / stubs_mod.SNAPSHOT_FILE, self.instructions)
                family = resolved[key]
        return (stubs_mod.origin(self.instructions, role, provider, family),
                stubs_mod.text(self.instructions, role, provider, family))

    def _save(self) -> None:
        self.store.save(self.state)

    def reports_dir(self) -> Path:
        return self.project / REPORTS / self.run_id

    def _catalog_get(self):
        if self._catalog is None:
            try:
                self._catalog = catalogs.Catalog.load(self.model_catalog, getattr(self.settings, "launch", None))
            except catalogs.CatalogError as error:
                raise Stop(error.code, str(error)) from None
        return self._catalog

    # ------------------------------------------------------------------ application: the verbs and the loop

    run = run_service.run
    resume = run_service.resume
    continue_run = run_service.continue_run
    _retry = run_service.retry
    _work_began = staticmethod(run_service.work_began)
    _batch_held = run_service.batch_held
    release = run_service.release
    settle = run_service.settle
    settle_group = run_service.settle_group
    _kill_orphaned_roles = recovery.kill_orphaned_roles
    _reconcile_interrupted = recovery.reconcile_interrupted

    _active_s = step_stage.active_s
    _disk_guard = step_stage.disk_guard
    _run_clock = step_stage.run_clock
    _loop = loop.loop
    _pieces = loop.pieces
    _claim_all = loop.claim_all
    _expand_ready = loop.expand_ready
    _decide_review_strategy = review_plan.decide
    _group_review_due = review_plan.group_review_due
    _per_piece_review_off = review_plan.per_piece_off
    _on_blocked = loop.on_blocked
    _dirty_paths = tree.dirty_paths
    _require_clean_tree = loop.require_clean_tree
    _claim_actor = loop.claim_actor
    _claim_actor_source = loop.claim_actor_source
    _invocation_executor = loop.invocation_executor
    _invocation_executor_class = loop.invocation_executor_class
    _piece = loop.piece
    _conduct = loop.conduct
    _step = step_stage.step
    _start_step = step_stage.start_step
    _stage_event = step_stage.stage_event
    _resolve = loop.resolve

    # ------------------------------------------------------------------ domain: the report of a piece

    _severity_of = staticmethod(report_rules.severity_of)
    _place = staticmethod(report_rules.place)
    _notes = staticmethod(report_rules.notes)

    def _plan_note(self, item: Item, text: str) -> None:
        """A plan note of the piece; it changes ``item.state``, so it is made under the run-store lock (I2)."""
        with self.store.mutating():
            report_rules.plan_note(item, text)

    def _review_debt(self, item: Item, review_round: int, findings: list, corrected: bool = True) -> None:
        """The last review round the wall allows found confirmed defects: they were corrected without another review.
        The piece goes on; ``review_debt`` in its state, the REVIEW_DEBT beacon and the observer report make it a
        place to look at after the plan (a second review round with findings hints at work handed over unfinished)."""
        debt = {"round": review_round, "findings": list(findings)}
        if not corrected:
            debt["corrected"] = False
        with self.store.mutating():
            if item.state.get("review_debt") == debt:  # a resume walks the closed rounds again: said once
                return
            item.state["review_debt"] = debt
            self._save()
        message = (f"review round {review_round} found {', '.join(findings)}; "
                   + ("corrected without a further review" if corrected else
                      "the final correction changed no product file: they stay open as plan notes")
                   + " (the review wall is reached)")
        self.progress.emit("info", item=item.ref, reason_code="REVIEW_DEBT", message=message)
        self._beacon_event("orch.run.warning", item, {"reason_code": "REVIEW_DEBT", "step": f"review.{review_round}"})

    _blocked = staticmethod(report_rules.blocked)

    # ------------------------------------------------------------------ infrastructure: the work source and the roles

    _orch = work_source.run_orch
    _claim = work_source.claim
    _release_claim = work_source.release_claim
    _brief = work_source.brief
    _brief_doc = work_source.brief_doc
    _prepare = work_source.prepare
    _refresh_input = work_source.refresh_input
    _research_save = work_source.research_save
    _record_decision = work_source.decision
    _register = work_source.register
    _commit = work_source.commit
    _open_artifacts = work_source.open_artifacts
    _local_records = work_source.local_records
    _write_artifact = work_source.write_artifact
    _evidence_dir = staticmethod(work_source.evidence_dir)
    _register_args = staticmethod(work_source.register_args)
    _closer_command = work_source.closer_command

    _agent_start = roles.agent_start
    _agent_end = roles.agent_end
    _agent_event = roles.agent_event
    _beacon_event = beacon_events.beacon_event
    _deviation_data = staticmethod(execute.deviation_data)
    _deviation_recorded = execute.deviation_recorded
    _deviation_resolved = execute.deviation_resolved
    _provider_limit = beacon_events.provider_limit
    _route_fallback = beacon_events.route_fallback
    _event_route = staticmethod(roles.event_route)
    _role = roles.run_role
    _denied = staticmethod(roles.denied)
    _role_body = roles.role_body
    _closed = staticmethod(results.closed)
    _repair = results.repair
    _beacons = roles.beacons
    _tokens = usage.add_tokens
    _relative = roles.relative
    _writes = staticmethod(launch_plan.writes)
    _tree_mark = tree.tree_mark
    _continuation = tree.continuation
    _role_argv = launch_plan.role_argv
    _extra_write_dirs = launch_plan.extra_write_dirs
    _claude_transcripts = launch_plan.claude_transcripts
    _scope_option = staticmethod(launch_plan.scope_option)
    _session_mode = staticmethod(sessions.session_mode)
    _shared_session = sessions.shared_session
    _resume_args = sessions.resume_args
    _keep_session = sessions.keep_session
    _delta_mode = sessions.delta_mode
    _announce_session = sessions.announce_session
    _session_slot = sessions.slot_of
    _answers_seen = sessions.answers_seen
    _note_answers = sessions.note_answers
    _role_env = launch_plan.role_env

    @property
    def role_ports(self) -> roles.RolePorts:
        """The ports of the role functions, built from the bindings of the layers above the infrastructure each time
        they are asked for: a run that is not opened (``role_argv`` of the dry run) has them too, and a binding a test
        replaces is the one called."""
        return roles.RolePorts(
            start_route=self._start_route, prompt_for_route=self._prompt_for_route,
            provider_failure=self._provider_failure, routed_blocks=self._routed_blocks, budget=self._budget,
            unmetered=self._unmetered, admit_budget=self._admit_budget, stage_key=self._stage_key,
            stage_bucket=self._stage_bucket, remember_stage=self._remember_stage,
            provider_disabled=self.provider_disabled, sandbox_args=self._sandbox_args, knows=self._knows,
            note_isolation=self._note_isolation, skills_excluded=self._skills_excluded, run_clock=self._run_clock)

    @property
    def panel_ports(self) -> advice.PanelPorts:
        """The route lookups of the advisor panel, from the bindings of the application layer when they are asked for."""
        return advice.PanelPorts(route=self._route, admit=self._admit)

    # ------------------------------------------------------------------ policies

    _allowance = limits_service.allowance
    _batch_allowance = limits_service.batch_allowance
    _limit_over = limits_service.limit_over
    _piece_count = staticmethod(allowance.piece_count)

    _entry = route_service.entry
    _launch_catalog = route_service.launch_catalog
    _launch_access = route_service.launch_access
    _routes = route_service.routes
    route_problem = route_service.route_problem
    provider_disabled = route_service.provider_disabled
    _selected = route_service.selected
    _fallback = route_service.fallback
    _admit = route_service.admit
    _refuse_acp = route_service.refuse_acp
    _preflight = route_service.preflight
    _route = route_service.route
    _route_minimum = route_service.route_minimum
    _reviewer_selector = route_service.reviewer_selector
    _bounded_corrections = route_service.bounded_corrections
    _correction_role = route_service.correction_role
    label = staticmethod(route_rules.label)
    _actor = staticmethod(route_rules.actor)

    _claude_sandbox_problem = route_service.claude_sandbox_problem
    _codex_sandboxed = staticmethod(sandbox_policy.codex_sandboxed)
    _sandbox_mode = staticmethod(sandbox_policy.sandbox_mode)
    _claude_bash = staticmethod(sandbox_policy.claude_bash)
    declared_network = staticmethod(sandbox_policy.declared_network)
    _sandbox_args = route_service.sandbox_args
    _knows = route_service.knows
    _note_isolation = route_service.note_plan
    _isolation_plan = launch_plan.isolation_plan

    _start_route = retry_service.start_route
    _prompt_for_route = retry_service.prompt_for_route
    _routed_blocks = retry_service.routed_blocks
    _provider_failure = retry_service.provider_failure
    _provider_stop = retry_service.provider_stop
    _gate = retry_service.gate
    _wait = retry_service.wait
    _pause = staticmethod(retry_policy.pause)

    _first_checks = staticmethod(risk_policy.first_checks)
    _recommended = staticmethod(risk_policy.recommended)
    _risk_facts = staticmethod(risk_policy.risk_facts)

    _budget = budget_service.budget
    _unmetered = budget_service.unmetered
    _admit_budget = budget_service.admit
    _bind_stage = budget_service.bind_stage
    _restore_stage = budget_service.restore_stage
    _stage_bucket = budget_service.stage_bucket
    _stage_key = budget_service.stage_key
    _remember_stage = budget_service.remember_stage

    # ------------------------------------------------------------------ the read-only facade of explain and the dry-run

    def preview_routes(self, item: Item) -> dict:
        """The options and the routes of ``item`` as ``run --dry-run`` shows them; the roles that cannot start."""
        self._resolve(item, persist=False)
        return self._routes(item, persist=False, preview=True) or {}

    def resolve_preview(self, item: Item) -> None:
        """The policy and the options of ``item`` without writing them."""
        self._resolve(item, persist=False)

    def route_for(self, item: Item, role: str, override: Optional[dict] = None) -> dict:
        return self._route(item, role, override)

    def selected_route(self, item: Item, role: str) -> dict:
        """The route of ``role`` route choice would take (a fallback when its own cannot start), nothing announced."""
        return self._selected(item, role, False)

    def admission(self, item: Item, role: str, route: dict) -> Optional[str]:
        return self._admit(item, role, route)

    def reviewer_for(self, item: Item) -> tuple:
        return self._reviewer_selector(item)

    def role_argv(self, item: Item, role: str, route: dict) -> list:
        """The command line of a role as the dry run shows it: built, not refused (a launch refuses it)."""
        return self._role_argv(item, role, route, admit=False)

    def sandbox_mode(self, item: Item) -> str:
        return self._sandbox_mode(item)

    def claude_bash(self, route: dict) -> bool:
        return self._claude_bash(route)

    def codex_sandboxed(self, route: dict) -> bool:
        return self._codex_sandboxed(route)

    def claim_actor(self) -> str:
        return self._claim_actor()

    # ------------------------------------------------------------------ stages

    _scout_stage = scout_stage.stage
    _scout = scout_stage.scout
    _hint = scout_stage.hint

    _research_wanted = research_stage.wanted
    _research_query = staticmethod(research_stage.query)
    _research = research_stage.research
    _research_command = research_stage.command
    _researched = staticmethod(research_stage.researched)
    _research_paths = staticmethod(research_stage.paths)

    _repo_rules = context.repo_rules
    _skills = context.skills
    _auto_skills = context.auto_skills
    _work_paths = context.work_paths
    _skill_files = context.skill_files
    _skill_body = staticmethod(context.skill_body)
    _route_tools = staticmethod(context.route_tools)
    _file_tools_rule = context.file_tools_rule
    _write_protected = context.write_protected
    _write_generated = context.write_generated
    _generated_globs = context.generated_globs
    _skill_set = context.skill_set
    _skills_excluded = context.skills_excluded
    _skill_texts = context.skill_texts

    _execute = execute.execute
    _round = execute.executor_round
    _batch_note = execute.batch_note
    _resumed_prompt = execute.resumed_prompt
    _autofixable = execute.autofixable
    _autofix = execute.autofix
    _self_check_return = execute.self_check_return
    _autofix_issues = execute.autofix_issues
    _questions = execute.questions
    _save_questions = execute.save_questions
    _questioned = execute.questioned
    _sync_questions = execute.sync_questions
    _changed_now = execute.changed_now
    _correction_baseline_files = correction.baseline_files
    _correction_scope = correction.scope
    _correction_settle = correction.settle
    _not_the_role = execute.not_the_role
    _changed = execute.changed
    _outside = execute.outside
    _expected_outside = staticmethod(execute.expected_outside)
    _adopted = execute.adopted

    _red_signature = staticmethod(checks_stage.red_signature)
    _green = checks_stage.green
    _product_snapshot = staticmethod(checks_stage.product_snapshot)
    _red_before = staticmethod(checks_stage.red_before)
    _earlier_rows = staticmethod(checks_stage.earlier_rows)
    _compute_checks = checks_stage.compute_checks
    _check_tick = checks_stage.check_tick
    _run_checks = checks_stage.run_checks
    _checks_then_review = checks_stage.checks_then_review
    _carry_review = checks_stage.carry_review

    _review_enabled = review_stage.review_enabled
    _reviewing = review_stage.reviewing
    _dynamic_review = review_stage.dynamic_review
    _review_requested_off = review_stage.requested_off
    _corrected = staticmethod(review_stage.corrected)
    _unresolved = staticmethod(review_stage.unresolved)
    _finding_paths = staticmethod(review_stage.finding_paths)
    _executor_advice = review_stage.executor_advice
    _review_focus = review_stage.review_focus
    _upgrade_reviewer = review_stage.upgrade_reviewer
    _review = review_stage.review
    _review_changed = review_stage.review_changed
    _review_base = review_stage.review_base
    _verdict_file = review_stage.verdict_file
    _corrected_receipt = review_stage.corrected_receipt

    _triage_role = triage_stage.role
    _triage = triage_stage.triage
    _split_confirmed = staticmethod(triage_stage.split_confirmed)
    _note_rejected = staticmethod(triage_stage.note_rejected)
    _defer_minor = staticmethod(triage_stage.defer_minor)

    _advisor_cfg = advice.advisor_cfg
    _advisor_on = advice.advisor_on
    _advice_slot = advice.advice_slot
    _advise = advice.advise
    _reading = advice.reading
    _advice_summary = staticmethod(advice.advice_summary)
    _advice_note = staticmethod(advice.advice_note)
    _advice_evidence = advice.advice_evidence
    _hold = advice.hold
    _owner_choice = staticmethod(advice.owner_choice)
    _advise_question = advice.advise_question
    _advise_red = advice.advise_red
    _retriage = advice.retriage

    _close = close.close
    _closer_named = staticmethod(close.closer_named)
    _finish = finish.finish
    _stage_commit = finish.stage_commit
    _splitting = finish.splitting
    _settle_pending = finish.settle_pending
