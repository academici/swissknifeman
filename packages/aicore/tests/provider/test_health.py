from unittest import TestCase

from core.provider.health import (
    HealthEvidence,
    HealthRequirement,
    evaluate_fleet,
    evaluate_project,
)


NOW = "2026-08-16T05:00:00Z"
FRESH = "2026-08-17T05:00:00Z"


def requirement(provider: str, axis: str, *, selected: bool = True,
                required: bool = True) -> HealthRequirement:
    return HealthRequirement(provider, axis, selected, required)


def evidence(provider: str, axis: str, state: str = "pass", *,
             expires_at: str = FRESH) -> HealthEvidence:
    return HealthEvidence(
        provider, axis, state, f"ev:{provider}:{axis}", f"owner:{axis}",
        "2026-08-15T05:00:00Z", expires_at,
    )


class ProviderHealthTests(TestCase):
    def test_green_result_is_ordered_and_digest_is_stable(self):
        requirements = (
            requirement("codex", "skill.runtime"),
            requirement("claude-code", "skill.runtime"),
        )
        observations = (
            evidence("codex", "skill.runtime"),
            evidence("claude-code", "skill.runtime"),
        )

        first = evaluate_project(
            project_id="project-a", requirements=requirements,
            evidence=observations, evaluated_at=NOW,
        )
        second = evaluate_project(
            project_id="project-a", requirements=tuple(reversed(requirements)),
            evidence=tuple(reversed(observations)), evaluated_at=NOW,
        )

        self.assertEqual("green", first.aggregate)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(["claude-code", "codex"], [row.provider_id for row in first.rows])
        self.assertRegex(first.result_digest, r"^sha256:[0-9a-f]{64}$")

    def test_one_provider_missing_cannot_be_masked(self):
        result = evaluate_project(
            project_id="project-a",
            requirements=(
                requirement("claude-code", "provider.readback"),
                requirement("codex", "provider.readback"),
            ),
            evidence=(evidence("claude-code", "provider.readback"),),
            evaluated_at=NOW,
        )

        self.assertEqual("non-green", result.aggregate)
        self.assertEqual("missing", result.rows[1].status)
        self.assertIn("PH_EVIDENCE_MISSING", {item.code for item in result.diagnostics})

    def test_required_unsupported_and_stale_are_non_green(self):
        unsupported = evaluate_project(
            project_id="project-a",
            requirements=(requirement("codex", "capability.memory"),),
            evidence=(evidence("codex", "capability.memory", "unsupported"),),
            evaluated_at=NOW,
        )
        stale = evaluate_project(
            project_id="project-a",
            requirements=(requirement("codex", "capability.memory"),),
            evidence=(evidence(
                "codex", "capability.memory", expires_at="2026-08-16T04:59:59Z",
            ),),
            evaluated_at=NOW,
        )

        self.assertIn("PH_REQUIRED_UNSUPPORTED", {item.code for item in unsupported.diagnostics})
        self.assertEqual("stale", stale.rows[0].status)
        self.assertEqual("non-green", stale.aggregate)

    def test_optional_unsupported_and_desired_not_selected_are_legal(self):
        result = evaluate_project(
            project_id="project-a",
            requirements=(
                requirement("codex", "capability.optional", required=False),
                requirement(
                    "third-provider", "provider.activation", selected=False, required=False,
                ),
            ),
            evidence=(
                evidence("codex", "capability.optional", "unsupported"),
                evidence("third-provider", "provider.activation", "not-selected"),
            ),
            evaluated_at=NOW,
        )

        self.assertEqual("green", result.aggregate)
        self.assertTrue(all(row.healthy for row in result.rows))

    def test_every_non_green_owner_state_remains_distinct(self):
        for state in ("unavailable", "unresolved", "unknown", "error"):
            with self.subTest(state=state):
                result = evaluate_project(
                    project_id="project-a",
                    requirements=(requirement("codex", "provider.readback"),),
                    evidence=(evidence("codex", "provider.readback", state),),
                    evaluated_at=NOW,
                )
                self.assertEqual(state, result.rows[0].status)
                self.assertEqual("non-green", result.aggregate)

        optional = evaluate_project(
            project_id="project-a",
            requirements=(requirement(
                "codex", "capability.optional", required=False,
            ),),
            evidence=(evidence("codex", "capability.optional", "not-required"),),
            evaluated_at=NOW,
        )
        self.assertEqual("green", optional.aggregate)

    def test_duplicate_and_extra_evidence_fail_closed(self):
        result = evaluate_project(
            project_id="project-a",
            requirements=(requirement("codex", "provider.readback"),),
            evidence=(
                evidence("codex", "provider.readback"),
                evidence("codex", "provider.readback"),
                evidence("codex", "provider.trust"),
            ),
            evaluated_at=NOW,
        )

        self.assertEqual("non-green", result.aggregate)
        self.assertEqual(
            {"PH_EVIDENCE_DUPLICATE", "PH_EVIDENCE_EXTRA"},
            {item.code for item in result.diagnostics},
        )

    def test_redaction_rejects_paths_and_secret_like_identity(self):
        for value in ("/home/alice/evidence", "secret-token"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "PH_REDACTION_REQUIRED",
            ):
                HealthEvidence(
                    "codex", "provider.readback", "pass", value, "owner:status",
                    "2026-08-15T05:00:00Z", FRESH,
                )

    def test_fleet_requires_exact_project_set(self):
        project = evaluate_project(
            project_id="project-a",
            requirements=(requirement("codex", "provider.readback"),),
            evidence=(evidence("codex", "provider.readback"),),
            evaluated_at=NOW,
        )
        fleet = evaluate_fleet(
            required_project_ids=("project-a", "project-b"),
            projects=(project,), evaluated_at=NOW,
        )

        self.assertEqual("non-green", fleet.aggregate)
        self.assertIn("PH_PROJECT_MISSING", {item.code for item in fleet.diagnostics})
