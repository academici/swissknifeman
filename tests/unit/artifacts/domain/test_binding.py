from skm.modules.artifacts.domain.binding import BindingRole


def test_binding_role_vocabulary() -> None:
    assert [r.value for r in BindingRole] == [
        "input",
        "reference",
        "deliverable",
        "evidence",
        "transcript",
        "patch",
        "report",
        "log",
        "prompt",
        "raw_result",
        "fix_brief",
        "diagnostic",
        "coverage_report",
        "stdout",
        "stderr",
        "diff",
    ]
