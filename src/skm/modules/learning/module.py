"""Manifest for learning evidence and human curation."""

from __future__ import annotations

from skm.kernel.module_manifest import ModuleManifest

from .application.commands.extract_candidates import CandidateExtracted
from .application.commands.promote_candidate import CandidatePromoted
from .application.commands.review_candidate import CandidateReviewed, CandidateStateChanged
from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .permissions import PERMISSIONS
from .ports import (
    ActivityRecordRepository,
    CandidateProposalRepository,
    CandidateRepository,
    CandidateReviewRepository,
    SignalRepository,
)

MODULE = ModuleManifest(
    id="learning",
    depends_on=("access", "workspace", "runtimes", "execution", "knowledge"),
    optional=True,
    db_schema="skm_learning",
    settings_sections=("learning",),
    permissions=PERMISSIONS,
    repository_ports=(
        ActivityRecordRepository,
        CandidateRepository,
        SignalRepository,
        CandidateReviewRepository,
        CandidateProposalRepository,
    ),
    gateway_ports=(),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=(),
    events=(CandidateExtracted, CandidatePromoted, CandidateReviewed, CandidateStateChanged),
)
