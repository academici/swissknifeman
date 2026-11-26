"""Factories for the PostgreSQL learning repository ports."""

from types import MappingProxyType

from skm.modules.learning.ports import (
    ActivityRecordRepository,
    CandidateProposalRepository,
    CandidateRepository,
    CandidateReviewRepository,
    SignalRepository,
)

from .activity import PostgresActivityRecordRepository
from .candidates import PostgresCandidateRepository
from .repositories import (
    PostgresCandidateProposalRepository,
    PostgresCandidateReviewRepository,
    PostgresSignalRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES = MappingProxyType(
    {
        ActivityRecordRepository: PostgresActivityRecordRepository,
        CandidateProposalRepository: PostgresCandidateProposalRepository,
        CandidateRepository: PostgresCandidateRepository,
        CandidateReviewRepository: PostgresCandidateReviewRepository,
        SignalRepository: PostgresSignalRepository,
    }
)
