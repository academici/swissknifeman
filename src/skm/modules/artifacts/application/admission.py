"""Content-safety scan and admission of a staged object inside a handler (artifacts §4.3, §7 add_file step 3).

The handler reads only the start of the object through the read-only ``BlobStore`` gateway (never writes
bytes) and applies ``scan_bytes`` then ``decide_admission``. An object the store no longer has is a forged or
stale ref: ``FILE_VERSION_NOT_READY``. A rejected admission raises, so the caller's unit of work rolls back
and the staged row stays unconsumed.

The rules, the acknowledgement floor and the default classification come from the effective configuration of
the **file's own** scope (``admission_policy``), read before the staged blob is touched: the workspace or the
project of the stored file, never the instance defaults a command without a scope of its own would carry.
"""

from dataclasses import dataclass

from skm.application_bus.context import CommandContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.modules.artifacts.application.reads import read_up_to
from skm.modules.artifacts.application.safety_rules import build_safety_rules
from skm.modules.artifacts.application.staging import StagedBlobView
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import (
    Admit,
    ContentKind,
    Reject,
    SafetyReport,
    SafetyRules,
    decide_admission,
    scan_bytes,
)
from skm.modules.artifacts.domain.file import FileOrigin
from skm.modules.artifacts.generated.settings import ArtifactsSettings
from skm.modules.artifacts.ports import BlobStore
from skm.platform.config.effective import EffectiveConfig

__all__ = [
    "AdmissionPolicy",
    "admission_policy",
    "content_kind",
    "scan_and_admit",
    "scan_staged",
]


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    """The configuration-derived inputs of one admission, resolved before any staged blob is consumed."""

    rules: SafetyRules
    acknowledge_floor: Classification
    default_classification: Classification


def admission_policy(config: EffectiveConfig) -> AdmissionPolicy:
    """Rules, acknowledgement floor and default classification of ``config``'s scope chain."""
    section = config.section(ArtifactsSettings)
    return AdmissionPolicy(
        rules=build_safety_rules(config),
        acknowledge_floor=Classification(section.safety.acknowledge_min_classification.value),
        default_classification=Classification(section.default_classification.value),
    )


def content_kind(origin: FileOrigin) -> ContentKind:
    """``evidence`` keeps an unsafe object (as ``restricted``); every other origin is an ordinary upload."""
    return ContentKind.EVIDENCE if origin is FileOrigin.EVIDENCE else ContentKind.UPLOAD


def scan_staged(
    store: BlobStore,
    staged: StagedBlobView,
    *,
    name: str,
    declared_media_type: str | None,
    rules: SafetyRules,
    kind: ContentKind,
) -> SafetyReport:
    try:
        stream = store.open(staged.location())
    except NotFound:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "the bytes of the staged blob are not in the store",
            details={"reason": "object_missing", "staged_blob_id": str(staged.staged_blob_id)},
        ) from None
    with stream:
        # A stream may hand out fewer bytes than asked for before its end: the probe and the scan must see
        # the same bytes whatever the chunking of the store.
        head = read_up_to(stream, rules.binary_probe_bytes)

        def read_all() -> bytes:
            return head + read_up_to(stream, rules.max_text_scan_bytes - len(head) + 1)

        return scan_bytes(
            name,
            head,
            read_all,
            staged.size_bytes,
            rules,
            kind,
            declared_media_type,
            staged.detected_media_type,
        )


def scan_and_admit(
    ctx: CommandContext,
    staged: StagedBlobView,
    *,
    policy: AdmissionPolicy,
    name: str,
    declared_media_type: str | None,
    origin: FileOrigin,
    classification: Classification,
    acknowledge: tuple[str, ...],
) -> Admit:
    kind = content_kind(origin)
    report = scan_staged(
        ctx.gateways.get(BlobStore),
        staged,
        name=name,
        declared_media_type=declared_media_type,
        rules=policy.rules,
        kind=kind,
    )
    admission = decide_admission(
        report, kind, classification, acknowledge, acknowledge_min_classification=policy.acknowledge_floor
    )
    if isinstance(admission, Reject):
        raise admission.error()
    if admission.escalated_by and kind is ContentKind.EVIDENCE:
        ctx.log.warning(
            "artifacts.evidence.restricted",
            file_name=name,
            rules=list(admission.escalated_by),
            staged_blob_id=str(staged.staged_blob_id),
        )
    return admission
