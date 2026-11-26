"""Binding roles: shared vocabulary of binding tables; a ref names one exact file version."""

from enum import StrEnum

from skm.kernel.json_types import JsonObject

__all__ = ["BindingRole", "FileVersionRef"]

type FileVersionRef = JsonObject


class BindingRole(StrEnum):
    INPUT = "input"
    REFERENCE = "reference"
    DELIVERABLE = "deliverable"
    EVIDENCE = "evidence"
    TRANSCRIPT = "transcript"
    PATCH = "patch"
    REPORT = "report"
    LOG = "log"
    PROMPT = "prompt"
    RAW_RESULT = "raw_result"
    FIX_BRIEF = "fix_brief"
    DIAGNOSTIC = "diagnostic"
    COVERAGE_REPORT = "coverage_report"
    STDOUT = "stdout"
    STDERR = "stderr"
    DIFF = "diff"
