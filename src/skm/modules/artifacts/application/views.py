"""Mapping of domain values to the generated views, results and DTO parts of artifacts (artifacts §7, §8).

Views carry what the spec lists and nothing physical: no blob id, no storage key, no location except the
``location`` of ``open_file_version_content`` (an address, never an access token).
"""

from collections.abc import Callable

from skm.modules.artifacts.domain.binding import FileVersionRef
from skm.modules.artifacts.domain.blob import Blob
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import File
from skm.modules.artifacts.domain.file_version import FileVersion, VersionSource
from skm.modules.artifacts.generated import commands, results, views

__all__ = [
    "add_file_safety",
    "add_version_safety",
    "file_summary",
    "file_version_ref",
    "file_view",
    "get_file_version_view",
    "source_from_command",
    "version_view",
]


def _classification(value: Classification) -> views.Classification:
    return views.Classification(value.value)


def version_view(version: FileVersion, blob: Blob) -> views.FileVersionView:
    return views.FileVersionView(
        file_version_id=version.id,
        version_no=version.version_no,
        original_filename=version.original_filename,
        size_bytes=blob.size_bytes,
        digest=blob.digest.value,
        declared_media_type=version.declared_media_type,
        detected_media_type=blob.detected_media_type,
        created_at=version.created_at,
        created_by=version.created_by,
        safety_verdict=version.safety.verdict(),
    )


def get_file_version_view(version: FileVersion, blob: Blob, file: File) -> views.GetFileVersionView:
    return views.GetFileVersionView(
        file_version_id=version.id,
        version_no=version.version_no,
        original_filename=version.original_filename,
        size_bytes=blob.size_bytes,
        digest=blob.digest.value,
        declared_media_type=version.declared_media_type,
        detected_media_type=blob.detected_media_type,
        created_at=version.created_at,
        created_by=version.created_by,
        safety_verdict=version.safety.verdict(),
        file_id=file.id,
        classification=_classification(file.classification),
        state=file.state.value,
    )


def file_summary(file: File) -> views.FileSummaryView:
    return views.FileSummaryView(
        file_id=file.id,
        workspace_id=file.workspace_id,
        project_id=file.project_id,
        title=file.title,
        origin=views.FileOrigin(file.origin.value),
        classification=_classification(file.classification),
        state=file.state.value,
        row_version=file.row_version,
    )


def file_view(file: File, current: views.FileVersionView) -> views.GetFileView:
    return views.GetFileView(
        file_id=file.id,
        workspace_id=file.workspace_id,
        project_id=file.project_id,
        title=file.title,
        origin=views.FileOrigin(file.origin.value),
        classification=_classification(file.classification),
        state=file.state.value,
        current_version=current,
        row_version=file.row_version,
    )


def file_version_ref(version: FileVersion) -> FileVersionRef:
    """The reference a caller binds to: one exact version of one file."""
    return {
        "file_id": str(version.file_id),
        "file_version_id": str(version.id),
        "version_no": version.version_no,
    }


def source_from_command(
    source: commands.AddFileDefsVersionSource | commands.AddFileVersionDefsVersionSource,
) -> VersionSource:
    return VersionSource(kind=source.kind, ref=source.ref, captured_at=source.captured_at)


def _findings[T](report: SafetyReport, make: Callable[..., T]) -> tuple[T, ...]:
    return tuple(
        make(
            rule=finding.rule,
            level=finding.level.value,
            detail=finding.detail,
            line=finding.line,
            pointer=finding.pointer,
        )
        for finding in report.findings
    )


def add_file_safety(report: SafetyReport) -> results.AddFileResultDefsSafetyReport:
    """The report in the shape of the ``add_file`` result (``safety_report`` of the artifacts defs)."""
    return results.AddFileResultDefsSafetyReport(
        verdict=report.verdict(),
        binary=report.binary,
        acknowledged=tuple(report.acknowledged),
        findings=_findings(report, results.AddFileResultDefsSafetyReportFindingsItem),
    )


def add_version_safety(report: SafetyReport) -> results.AddFileVersionResultDefsSafetyReport:
    """The same report in the shape of the ``add_file_version`` result."""
    return results.AddFileVersionResultDefsSafetyReport(
        verdict=report.verdict(),
        binary=report.binary,
        acknowledged=tuple(report.acknowledged),
        findings=_findings(report, results.AddFileVersionResultDefsSafetyReportFindingsItem),
    )
