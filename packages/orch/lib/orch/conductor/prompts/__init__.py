"""Prompts of the roles the conductor starts, and the closed result each one returns.

A prompt is the role text and the task block of ``render.render_prompt`` (the execution-input only: the role never
sees the plan or the plan command line), followed by the conductor frame: the scout context, the run rules, a
correction package, the candidate under review, and the result block the role must end with. Every role prints the
same progress lines as the conductor (``[orch] <item> <step> <what>``) before each major step.

Every builder returns the prompt as a list of ``Block(kind, origin, text)``; ``render`` joins them into the prompt byte for
byte (a separator belongs to the block it follows), and ``manifest`` says what each block is and where it came from.

The package keeps the API of the module it replaced: ``blocks`` (Block, render, joins, digest), ``contracts`` (the result
texts), ``manifest`` (the manifest and its diff), ``roles`` (the builder of each role) and ``corrections`` (the
correction packages). Callers keep using ``prompts.<name>``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace  # noqa: F401 — kept: the names the module had
import json  # noqa: F401
from pathlib import Path  # noqa: F401
import re  # noqa: F401
from typing import Optional  # noqa: F401

from aicore.content.budget import estimate_tokens  # noqa: F401
from aicore.util.digest import sha256_hex  # noqa: F401

from orch import render as role_render  # noqa: F401
from orch.conductor import records  # noqa: F401
from orch.conductor.domain.report import json_block, write_set_block  # noqa: F401 — the answer parsers, kept here
from orch.conductor.policies.budget import BUDGET_CLASSES, BUDGET_LIMITS, budget_class, budgets, over_budget  # noqa: F401
from orch.conductor.policies.skills import EXCLUSIVE_GROUP_LIMITS, EXCLUSIVE_GROUP_MAX, INTERACTIVE_TOOL, check_skills  # noqa: F401

from orch.conductor.prompts.blocks import (  # noqa: F401
    BATCH_ID, CONDUCTOR, KINDS, ROUND_KINDS, Block, _fence, _join, _progress, _then, render, task_digest,
    with_operator_context)
from orch.conductor.prompts.contracts import (  # noqa: F401
    CONTRACT_TEXT, RESULT_KINDS, _ADVICE, _PROGRESS, _RESEARCH_RESULT, _REVIEW_FINDINGS, _STAGE_REPORT, _TRIAGE_RESULT)
from orch.conductor.prompts.corrections import (  # noqa: F401
    ADOPTED, DEVIATION_FIX, _CHILD_LOG, _FAILURE_HEADER, _NO_DIFF_RULE, _answers, _correction, _failure_excerpt,
    _failure_report, _historical_causes, _self_check_again, advice_correction, advice_for_triage, advice_text,
    check_correction, evidence, fix_deviation, interrupted_correction, review_correction, self_check_missing)
from orch.conductor.prompts.manifest import diff_manifests, diff_table, explain_table, manifest, top_blocks  # noqa: F401
from orch.conductor.prompts.roles import (  # noqa: F401
    CHANGED_PATHS, _FILE_TOOLS_RULE, _PRE_FINAL, _RUN_CHECKS, _conductor_checks, _corrected_scope, _diff_title, _expected,
    _fence_rule, _focus, _head, _outside_scope, _research, _self_check, advisor, closer, executor, executor_resumed,
    generated_rule, protected_rule, report_fixer, researcher, retarget, reviewer, scout, triager, with_containers)
