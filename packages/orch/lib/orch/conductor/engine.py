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
from orch.conductor.application import loop, recovery, review_plan, run_service
from orch.conductor.domain import report as report_rules
from orch.conductor.domain.item import Item
from orch.conductor.domain.report import continued, evidence_paths, findings_problems, report_problems
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import beacon_events, roles, work_source
from orch.conductor.infrastructure.clock import new_run_id, sleep, unit_random, utc_now, utc_stamp, wall
from orch.conductor.infrastructure.files import (OPTIONS_COPY, REPORTS, RUN_FILE, STATE_FILE, RunStore, read_json,
                                                 runs_root, safe, write_json)
from orch.conductor.infrastructure.work_source import FALLBACK_ARTIFACTS
from orch.conductor.policies import allowance, budget, retry_policy, routing
from orch.conductor.policies import risk as risk_policy, sandbox as sandbox_policy
from orch.conductor.policies.allowance import BATCH_FIELDS, BATCH_LIMITS
from orch.conductor.policies.routing import CLASS_RANK, EFFORT_RANK, LAUNCH_ROLE
from orch.conductor import stubs as stubs_mod
from orch.conductor.progress import Progress
from orch.conductor.stages import advice, checks_stage, close, context, execute, finish
from orch.conductor.stages import research as research_stage, review as review_stage, scout as scout_stage
from orch.conductor.stages import triage as triage_stage
from orch.settings import ORCH_ROOT

# The names other modules and the tests import from here. ``process`` and ``sandbox`` are the modules the tests patch
# (``process.available``, ``process.run_role``, ``sandbox.probe``); the clocks are patched in ``infrastructure.clock``.
__all__ = ["BATCH_FIELDS", "BATCH_LIMITS", "CLASS_RANK", "Conductor", "EFFORT_RANK", "FALLBACK_ARTIFACTS", "Item",
           "LAUNCH_ROLE", "OPTIONS_COPY", "ORCH_ROOT", "REPORTS", "RUN_FILE", "RunStore", "STATE_FILE", "STATUS_EXIT", "Stop",
           "continued", "evidence_paths", "findings_problems", "new_run_id", "process", "read_json", "report_problems",
           "runs_root", "safe", "sandbox", "sleep", "unit_random", "utc_now", "utc_stamp", "wall", "write_json"]

STATUS_EXIT = {"finished": 0, "stopped": 1}


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
        self._step_tokens = {"input": 0, "output": 0}
        self._local = threading.local()  # the agent run of the role this thread runs: usage and children belong to it
        self.run_id = ""
        self.directory = Path()
        self.store: Optional[RunStore] = None
        self.run_doc: dict = {}
        self.state: dict = {}
        self.progress: Optional[Progress] = None
        self.instructions: dict = {}  # the stubs snapshot of the run (``instructions.json``)
        self._instructions_lock = threading.Lock()

    _current_step: Optional[str] = None  # the step that runs now, for the RUN_SLOW beacon
    _sandbox_noted = False  # ISOLATION_PARTIAL of a sandbox that cannot start is said once per run

    # ------------------------------------------------------------------ run files

    def _open(self, run_id: str, run_doc: dict, state: dict, store: Optional[RunStore] = None) -> None:
        self.run_id, self.run_doc, self.state = run_id, run_doc, state
        self.store = store or RunStore(self.project, run_id)
        self.directory = self.store.directory
        self.progress = Progress(run_id, self.directory, self.mode, self.stream, self.clock)
        self.instructions = read_json(self.directory / stubs_mod.SNAPSHOT_FILE) or {}

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
    _retry = run_service.retry
    _work_began = staticmethod(run_service.work_began)
    _batch_held = run_service.batch_held
    release = run_service.release
    settle = run_service.settle
    _kill_orphaned_roles = recovery.kill_orphaned_roles
    _reconcile_interrupted = recovery.reconcile_interrupted

    _active_s = loop.active_s
    _disk_guard = loop.disk_guard
    _run_clock = loop.run_clock
    _loop = loop.loop
    _pieces = loop.pieces
    _claim_all = loop.claim_all
    _expand_ready = loop.expand_ready
    _decide_review_strategy = review_plan.decide
    _group_review_due = review_plan.group_review_due
    _per_piece_review_off = review_plan.per_piece_off
    _on_blocked = loop.on_blocked
    _dirty_paths = loop.dirty_paths
    _require_clean_tree = loop.require_clean_tree
    _claim_actor = loop.claim_actor
    _claim_actor_source = loop.claim_actor_source
    _invocation_executor = loop.invocation_executor
    _invocation_executor_class = loop.invocation_executor_class
    _piece = loop.piece
    _conduct = loop.conduct
    _step = loop.step
    _start_step = loop.start_step
    _stage_event = loop.stage_event
    _resolve = loop.resolve

    # ------------------------------------------------------------------ domain: the report of a piece

    _severity_of = staticmethod(report_rules.severity_of)
    _place = staticmethod(report_rules.place)
    _notes = staticmethod(report_rules.notes)

    def _plan_note(self, item: Item, text: str) -> None:
        """A plan note of the piece; it changes ``item.state``, so it is made under the run-store lock (I2)."""
        with self.store.mutating():
            report_rules.plan_note(item, text)

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
    _closed = staticmethod(roles.closed)
    _repair = roles.repair
    _beacons = roles.beacons
    _tokens = roles.add_tokens
    _relative = roles.relative
    _writes = staticmethod(roles.writes)
    _tree_mark = roles.tree_mark
    _continuation = roles.continuation
    _role_argv = roles.role_argv
    _extra_write_dirs = roles.extra_write_dirs
    _claude_transcripts = roles.claude_transcripts
    _scope_option = staticmethod(roles.scope_option)
    _session_mode = staticmethod(roles.session_mode)
    _shared_session = roles.shared_session
    _resume_args = roles.resume_args
    _keep_session = roles.keep_session
    _delta_mode = roles.delta_mode
    _role_env = roles.role_env

    # ------------------------------------------------------------------ policies

    _allowance = allowance.allowance
    _batch_allowance = allowance.batch_allowance
    _limit_over = allowance.limit_over
    _piece_count = staticmethod(allowance.piece_count)

    _entry = routing.entry
    _launch_catalog = routing.launch_catalog
    _launch_access = routing.launch_access
    _routes = routing.routes
    route_problem = routing.route_problem
    provider_disabled = routing.provider_disabled
    _selected = routing.selected
    _fallback = routing.fallback
    _admit = routing.admit
    _refuse_acp = routing.refuse_acp
    _preflight = routing.preflight
    _route = routing.route
    _route_minimum = routing.route_minimum
    _reviewer_selector = routing.reviewer_selector
    label = staticmethod(routing.label)
    _actor = routing.actor

    _claude_sandbox_problem = sandbox_policy.claude_sandbox_problem
    _codex_sandboxed = staticmethod(sandbox_policy.codex_sandboxed)
    _sandbox_mode = staticmethod(sandbox_policy.sandbox_mode)
    _claude_bash = staticmethod(sandbox_policy.claude_bash)
    declared_network = staticmethod(sandbox_policy.declared_network)
    _sandbox_args = sandbox_policy.sandbox_args
    _knows = sandbox_policy.knows

    _start_route = retry_policy.start_route
    _prompt_for_route = retry_policy.prompt_for_route
    _routed_blocks = retry_policy.routed_blocks
    _provider_failure = retry_policy.provider_failure
    _provider_stop = retry_policy.provider_stop
    _gate = retry_policy.gate
    _wait = retry_policy.wait
    _pause = staticmethod(retry_policy.pause)

    _first_checks = staticmethod(risk_policy.first_checks)
    _recommended = staticmethod(risk_policy.recommended)
    _risk_facts = risk_policy.risk_facts

    _budget = budget.budget
    _unmetered = budget.unmetered
    _admit_budget = budget.admit

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
    _skill_set = context.skill_set
    _skills_excluded = context.skills_excluded
    _skill_texts = context.skill_texts

    _execute = execute.execute
    _round = execute.executor_round
    _batch_note = execute.batch_note
    _resumed_prompt = execute.resumed_prompt
    _autofixable = execute.autofixable
    _autofix = execute.autofix
    _autofix_issues = execute.autofix_issues
    _questions = execute.questions
    _save_questions = execute.save_questions
    _questioned = execute.questioned
    _sync_questions = execute.sync_questions
    _changed_now = execute.changed_now
    _not_the_role = execute.not_the_role
    _changed = execute.changed
    _outside = execute.outside
    _expected_outside = staticmethod(execute.expected_outside)
    _adopted = execute.adopted

    _red_signature = staticmethod(checks_stage.red_signature)
    _green = checks_stage.green
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
    _verdict_file = review_stage.verdict_file

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
    _settle_pending = finish.settle_pending
