"""Proposed investigations for recurring pathology findings."""

from .pathology import PathologyCode

REMEDIATIONS: dict[PathologyCode, str] = {
    PathologyCode.FILE_REREAD: "keep a short map of files already read; consult it instead of re-reading",
    PathologyCode.TOOL_ERROR_LOOP: (
        "after two identical tool failures change the approach instead of retrying the same call"
    ),
    PathologyCode.NO_VERIFY: "after changing code run the project checks before finishing",
    PathologyCode.PROTECTED_WRITE: (
        'do not edit files managed by skm projections; change the source and run "skm integrations apply"'
    ),
}
