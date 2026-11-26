"""Factories for the implemented learning repository ports."""

from types import MappingProxyType

from skm.modules.learning.ports import (
    ActivityRecordRepository,
    CandidateProposalRepository,
    CandidateRepository,
    CandidateReviewRepository,
    SignalRepository,
)

from .activity import MemoryActivityRecordRepository
from .candidates import MemoryCandidateRepository
from .proposals import MemoryCandidateProposalRepository
from .reviews import MemoryCandidateReviewRepository
from .signals import MemorySignalRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES = MappingProxyType(
    {
        ActivityRecordRepository: MemoryActivityRecordRepository,
        CandidateRepository: MemoryCandidateRepository,
        CandidateProposalRepository: MemoryCandidateProposalRepository,
        CandidateReviewRepository: MemoryCandidateReviewRepository,
        SignalRepository: MemorySignalRepository,
    }
)
