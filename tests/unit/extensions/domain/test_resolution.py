"""Choice of pack versions and resources (extensions §4.1, §4.12, §4.14, K19).

Priority, trust and slug order; quarantine; digest and version pins; a missing pack; constraints;
``PackPins``: a newer installed version and a disabled pack change nothing, a retired or foreign pinned
version is ``pinned_pack_missing``. The version and digest rules every choice relies on are here too.
"""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from itertools import pairwise
from uuid import UUID, uuid4

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ResourceVersionId
from skm.kernel.outcomes import Severity
from skm.modules.extensions.domain.compat import CompatVerdict
from skm.modules.extensions.domain.digest_rules import is_excluded, pack_digest, resource_digest
from skm.modules.extensions.domain.keys import (
    LATEST,
    PackId,
    PackVersionId,
    SemVer,
    VersionConstraint,
    parse_pack_slug,
    parse_resource_key,
)
from skm.modules.extensions.domain.kinds import (
    KIND_SPECS,
    ResourceKind,
    is_root_file,
    locate,
    validate_layout,
)
from skm.modules.extensions.domain.pack import PackState, PackTrust, PackVersionSummary
from skm.modules.extensions.domain.resolution import (
    PackChoice,
    ResolutionOutcome,
    choices_from_pins,
    choose_pack_versions,
    parse_resource_pin,
    require_chosen,
    resolve,
)
from skm.modules.extensions.domain.resource import ResourceVersionSummary
from skm.platform.jsonc.digest import digest

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
KIND = ResourceKind.AGENT_PROFILE
KEY = "executor"


def installed(
    slug: str = "core",
    version: str = "1.0.0",
    *,
    state: PackState = PackState.ACTIVE,
    trust: PackTrust = PackTrust.BUILTIN,
    priority: int = 0,
) -> PackVersionSummary:
    return PackVersionSummary(
        version_id=PackVersionId(uuid4()),
        pack_id=PackId(UUID(int=abs(hash(slug)))),
        slug=slug,
        title=slug,
        trust=trust,
        version=SemVer.parse(version),
        digest="sha256:" + "a" * 64,
        priority=priority,
        state=state,
        installed_at=NOW,
    )


def choice_of(row: PackVersionSummary) -> PackChoice:
    return PackChoice(row.pack_id, row.slug, row.version_id, row.version, row.trust, row.priority)


def version_in(
    row: PackVersionSummary | PackChoice, *, digest: str = "b", key: str = KEY, version: str = "1.0.0"
) -> ResourceVersionSummary:
    pack_version = row.version_id
    return ResourceVersionSummary(
        id=ResourceVersionId(uuid4()),
        kind=KIND,
        key=key,
        pack_version_id=pack_version,
        version=SemVer.parse(version),
        digest="sha256:" + digest * 64,
        verdict=CompatVerdict.CLEAN,
    )


# ---------------------------------------------------------------------------------------- versions and keys
def test_semver_orders_by_precedence_not_by_text() -> None:
    ordered = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0",
        "1.9.0",
    ]
    ordered.append("1.10.0")
    parsed = [SemVer.parse(text) for text in ordered]
    backwards = parsed[::-1]
    assert sorted(backwards, key=lambda version: version._order()) == parsed
    assert all(earlier < later for earlier, later in pairwise(parsed))
    assert str(parsed[3]) == "1.0.0-beta.2"


@pytest.mark.parametrize(
    "text",
    [
        "1.0",
        "01.0.0",
        "1.0.0+build",
        "1.0.0-",
        "v1.0.0",
        "",
        "1.0.0-01",
        "1.0.0-alpha.01",
        "1.0.0-00",
        "1.0.0-a..b",
    ],
)
def test_semver_refuses_what_is_not_strict(text: str) -> None:
    with pytest.raises(ValidationFailed) as refused:
        SemVer.parse(text)
    assert refused.value.code is ErrorCode.SCHEMA_INVALID


@pytest.mark.parametrize(
    "text", ["1.0.0-0", "1.0.0-1", "1.0.0-10", "1.0.0-0a", "1.0.0-01a", "1.0.0--", "1.0.0-a.0"]
)
def test_semver_keeps_every_valid_prerelease(text: str) -> None:
    assert str(SemVer.parse(text)) == text


def test_a_constraint_refuses_a_prerelease_that_is_not_strict() -> None:
    assert str(VersionConstraint.parse(">=1.0.0-rc.1")) == ">=1.0.0-rc.1"
    with pytest.raises(ValidationFailed):
        VersionConstraint.parse(">=1.0.0-01")


def test_constraints() -> None:
    range_ = VersionConstraint.parse(">=1.2.0,<2")
    assert range_.matches(SemVer.parse("1.2.0"))
    assert range_.matches(SemVer.parse("1.99.0"))
    assert not range_.matches(SemVer.parse("2.0.0"))
    assert not range_.matches(SemVer.parse("1.1.9"))
    exact = VersionConstraint.parse("1.2.3")
    assert exact.matches(SemVer.parse("1.2.3"))
    assert not exact.matches(SemVer.parse("1.2.4"))
    assert VersionConstraint.parse("latest") is LATEST
    assert LATEST.matches(SemVer.parse("0.0.1"))
    assert VersionConstraint.parse(str(range_)) == range_
    for bad in ("^1.2.0", "~1.2", "nonsense"):
        with pytest.raises(ValidationFailed):
            VersionConstraint.parse(bad)


def test_keys_of_prompt_blocks_differ_from_the_others() -> None:
    assert parse_resource_key("shared/system_constraints", prompt_block=True) == "shared/system_constraints"
    assert parse_pack_slug("core") == "core"
    for bad, prompt in (("shared/x", False), ("plain", True), ("A", False), ("x", False)):
        with pytest.raises(ValidationFailed):
            parse_resource_key(bad, prompt_block=prompt)
    with pytest.raises(ValidationFailed):
        parse_pack_slug("Bad_Slug")


def test_paths_locate_their_resource_and_nothing_else() -> None:
    assert locate("skills/review/references/a.md") == (located := locate("skills/review/references/a.md"))
    assert located is not None
    assert (located.kind, located.key, located.inner) == (
        ResourceKind.SKILL,
        "review",
        "references/a.md",
    )
    prompt = locate("prompts/shared/run_rules.md")
    assert prompt is not None
    assert (prompt.kind, prompt.key, prompt.inner) == (
        ResourceKind.PROMPT_BLOCK,
        "shared/run_rules",
        "run_rules.md",
    )
    catalog = locate("runtimes/models.toml")
    assert catalog is not None
    assert (catalog.kind, catalog.key) == (ResourceKind.RUNTIME_CATALOG, "models")
    guideline = locate("model-guidelines/grok-4-7.toml")
    assert guideline is not None
    assert (guideline.kind, guideline.key, guideline.inner) == (
        ResourceKind.MODEL_GUIDELINE,
        "grok-4-7",
        "grok-4-7.toml",
    )
    for outside in ("policy-profiles/x.toml", "evals/x.md", "agent-profiles/x.md", "other.txt"):
        assert locate(outside) is None


def test_layout_reports_limits_and_missing_files() -> None:
    skill = KIND_SPECS[ResourceKind.SKILL]
    reasons = {
        item.reason for item in validate_layout(skill, {"SKILL.md": b"x" * (skill.max_file_bytes + 1)})
    }
    assert reasons == {"file_too_large", "manifest_missing"}
    assert validate_layout(skill, {"SKILL.md": b"x", "manifest.toml": b"x"}) == ()


# ---------------------------------------------------------------------------------------- digests
def test_resource_digest_is_the_legacy_algorithm_and_independent_of_order() -> None:
    files = {"b/two.md": b"2", "a.md": b"1"}
    expected = hashlib.sha256(b"a.md\x001b/two.md\x002").hexdigest()
    assert resource_digest(files) == f"sha256:{expected}"
    assert resource_digest(dict(reversed(files.items()))) == resource_digest(files)
    assert resource_digest({"c.md": b"1", "b/two.md": b"2"}) != resource_digest(files)  # a rename changes it


def test_excluded_files_do_not_change_a_digest() -> None:
    base = {"SKILL.md": b"x"}
    for path in ("__pycache__/a.cpython.pyc", "tool.pyc", "SKILL.ru.md", ".DS_Store", "deep/__pycache__/x"):
        assert is_excluded(path)
        assert resource_digest({**base, path: b"noise"}) == resource_digest(base)
    assert not is_excluded("SKILL.md")


# A skill of the legacy shape as literal bytes; no donor package is imported. The hex below comes from
# ``printf 'SKILL.md\0# Review\nreferences/a.md\0ref\nsnippets/run.py\0print(1)\n' | sha256sum``.
LEGACY_CONTENT = {"SKILL.md": b"# Review\n", "references/a.md": b"ref\n", "snippets/run.py": b"print(1)\n"}
LEGACY_CONTENT_HEX = "dbadf7f59a6e952f483604f5d766965b1a8188d2a82a498134b4d1d098ec7f23"
LEGACY_ONLY_SKIPPED = (  # the legacy hash skips them; §4.14 does not, they cannot reach it in a v2 pack
    "upstream.json",
    "selection.json",
    "compat-report.json",
    "evals/evals.json",
    ".claude-plugin/plugin.json",
)


def test_the_digest_equals_the_literal_vector_on_the_same_file_set() -> None:
    assert resource_digest(LEGACY_CONTENT) == f"sha256:{LEGACY_CONTENT_HEX}"
    # Bytecode and localized files stay out of the digest function; ingestion refuses them before it.
    noise = {"SKILL.ru.md": b"x", "__pycache__/a.pyc": b"x", "snippets/run.pyc": b"x"}
    assert resource_digest({**LEGACY_CONTENT, **noise}) == f"sha256:{LEGACY_CONTENT_HEX}"


def test_paths_sort_as_whole_posix_strings() -> None:
    """``-`` sorts before ``/``: the order by whole strings differs from the order by path segments."""
    expected = "e1d1512f60164f28429ef67f80e25618711ac9b2e3b2c8870d07b553bf7bb9b1"
    assert resource_digest({"a/x": b"1", "a-b/x": b"2"}) == f"sha256:{expected}"


@pytest.mark.parametrize("path", LEGACY_ONLY_SKIPPED)
def test_a_legacy_sidecar_is_never_silently_omitted(path: str) -> None:
    """No parity is pretended here: on the same tree a v2 digest differs from the legacy hash."""
    assert not is_excluded(path)
    assert resource_digest({**LEGACY_CONTENT, path: b"{}"}) != f"sha256:{LEGACY_CONTENT_HEX}"


def test_a_v2_skill_with_its_manifest_is_not_the_legacy_vector() -> None:
    """``manifest.toml`` is in the digest and has no legacy counterpart: no import can compare the two."""
    assert resource_digest({**LEGACY_CONTENT, "manifest.toml": b"x"}) != f"sha256:{LEGACY_CONTENT_HEX}"


@pytest.mark.parametrize(
    "path",
    [
        "upstream.json",
        "selection.json",
        "compat-report.json",
        "evals/evals.json",
        ".claude-plugin/plugin.json",
        "SKILL.ru.md",
        ".DS_Store",
        "references/.DS_Store",
        "references/tool.pyc",
        "examples/__pycache__/run.py",
        "run.py",
        "references",
        "scripts/run.sh",
        "References/a.md",
    ],
)
def test_a_skill_holds_only_what_its_layout_lists(path: str) -> None:
    skill = KIND_SPECS[ResourceKind.SKILL]
    files = {"SKILL.md": b"x", "manifest.toml": b"x", path: b"x"}
    assert [(item.reason, item.path) for item in validate_layout(skill, files)] == [("unexpected_file", path)]


def test_the_layout_of_a_skill_admits_its_directories() -> None:
    skill = KIND_SPECS[ResourceKind.SKILL]
    files = {
        "SKILL.md": b"x",
        "manifest.toml": b"x",
        "references/a/b.md": b"x",
        "snippets/run.py": b"x",
        "examples/e.md": b"x",
    }
    assert validate_layout(skill, files) == ()


def test_a_plan_template_holds_only_its_two_files() -> None:
    template = KIND_SPECS[ResourceKind.PLAN_TEMPLATE]
    assert validate_layout(template, {"manifest.toml": b"x", "template.json": b"x"}) == ()
    found = validate_layout(template, {"manifest.toml": b"x", "run.py": b"x"})
    assert [(item.reason, item.path) for item in found] == [("unexpected_file", "run.py")]


@pytest.mark.parametrize("path", ["tool.pyc", "lib/__pycache__/run.py", ".DS_Store", "SKILL.ru.md"])
def test_a_bundle_cannot_carry_a_file_its_digest_skips(path: str) -> None:
    """A bundle holds any files (§4.2), so bytes outside the digest could be executable here."""
    bundle = KIND_SPECS[ResourceKind.INTEGRATION_BUNDLE]
    found = validate_layout(bundle, {"bundle.toml": b"x", "hooks/run.py": b"x", path: b"x"})
    assert [(item.reason, item.path) for item in found] == [("unexpected_file", path)]


def test_root_files_are_files_of_the_root() -> None:
    for root in ("pack.toml", "README.md", "LICENSE", "LICENSE-MIT", "CHANGELOG.md"):
        assert is_root_file(root)
    for nested in ("LICENSE/run.py", "LICENSE-MIT/tool.pyc", "docs/README.md"):
        assert not is_root_file(nested)
        assert locate(nested) is None


def test_pack_digest_covers_manifest_and_rows_in_any_order() -> None:
    rows = [("skill", "a", "1.0.0", "sha256:1"), ("skill", "b", "1.0.0", "sha256:2")]
    assert pack_digest({"slug": "x"}, rows) == pack_digest({"slug": "x"}, list(reversed(rows)))
    assert pack_digest({"slug": "x"}, rows) != pack_digest({"slug": "y"}, rows)
    assert pack_digest({"slug": "x"}, rows) != pack_digest({"slug": "x"}, rows[:1])
    assert pack_digest({"rate": 0.5}, rows).startswith(
        "sha256:"
    )  # a TOML float must not break canonical JSON


def test_pack_digest_is_the_canonical_json_v1_digest() -> None:
    """The domain cannot import ``platform.jsonc``; its digest must stay byte-identical to it."""
    rows = [("skill", "b", "1.0.0", "sha256:2"), ("skill", "a", "1.0.0", "sha256:1")]
    manifest = {"slug": "é", "nested": {"z": 1, "a": [True, None]}}
    expected = {"manifest": manifest, "resources": [list(row) for row in sorted(rows)]}
    assert pack_digest(manifest, rows) == digest(expected)


# ---------------------------------------------------------------------------------------- pack versions
def test_newest_allowed_active_version_is_chosen_by_semver() -> None:
    rows = [
        installed(version="1.9.0"),
        installed(version="1.10.0"),
        installed(version="2.0.0-rc.1"),
        installed(version="3.0.0", state=PackState.RETIRED),
    ]
    choices, diagnostics = choose_pack_versions(["core"], {}, rows)
    assert [str(item.version) for item in choices] == ["2.0.0-rc.1"]
    assert diagnostics == ()
    limited, _ = choose_pack_versions(["core"], {"core": VersionConstraint.parse(">=1.0.0,<1.99")}, rows)
    assert [str(item.version) for item in limited] == ["1.10.0"]


def test_an_unknown_or_unfitting_pack_is_a_diagnostic_and_others_still_resolve() -> None:
    rows = [installed("extra", "1.0.0")]
    choices, diagnostics = choose_pack_versions(
        ["core", "extra", "extra"], {"extra": VersionConstraint.parse("<2")}, rows
    )
    assert [item.slug for item in choices] == ["extra"]
    assert [(item.code, item.severity, item.target) for item in diagnostics] == [
        ("PACK_NOT_INSTALLED", Severity.ERROR, "core")
    ]


def test_configured_priority_replaces_the_priority_of_the_version() -> None:
    choices, _ = choose_pack_versions(["core"], {}, [installed(priority=5)], priorities={"core": 700})
    assert choices[0].priority == 700


# ---------------------------------------------------------------------------------------- resolve
def test_order_is_priority_then_trust_then_slug() -> None:
    builtin = installed("aaa", priority=10)
    operator = installed("bbb", priority=10, trust=PackTrust.OPERATOR)
    stronger = installed("zzz", priority=20, trust=PackTrust.THIRD_PARTY)
    tie = installed("ccc", priority=10, trust=PackTrust.OPERATOR)
    rows = [builtin, operator, stronger, tie]
    choices = [choice_of(row) for row in rows]
    versions = [version_in(row, digest=str(index)) for index, row in enumerate(rows)]
    decision = resolve(KIND, KEY, choices, versions, frozenset(), None)
    assert [row.pack for row in decision.candidates] == ["zzz", "bbb", "ccc", "aaa"]
    assert decision.chosen == versions[2]
    assert [row.reason for row in decision.candidates] == ["chosen"] + ["lower_priority"] * 3
    without_strong = resolve(KIND, KEY, choices[:2] + choices[3:], versions, frozenset(), None)
    assert [row.pack for row in without_strong.candidates] == ["bbb", "ccc", "aaa"]


def test_the_first_candidate_outside_quarantine_wins() -> None:
    high, low = installed("high", priority=10), installed("low", priority=1)
    versions = [version_in(high, digest="1"), version_in(low, digest="2")]
    decision = resolve(
        KIND, KEY, [choice_of(high), choice_of(low)], versions, frozenset({versions[0].id}), None
    )
    assert decision.chosen == versions[1]
    assert [row.reason for row in decision.candidates] == ["quarantined", "chosen"]


def test_all_quarantined_is_refused() -> None:
    row = installed()
    version = version_in(row)
    decision = resolve(KIND, KEY, [choice_of(row)], [version], frozenset({version.id}), None)
    assert decision.chosen is None
    assert decision.outcome is ResolutionOutcome.QUARANTINED
    with pytest.raises(PreconditionFailed) as refused:
        require_chosen(decision)
    assert refused.value.code is ErrorCode.RESOURCE_QUARANTINED


def test_no_candidate_is_not_found_with_the_pair_or_the_missing_pack() -> None:
    decision = resolve(KIND, KEY, [choice_of(installed())], [], frozenset(), None)
    assert decision.outcome is ResolutionOutcome.NO_CANDIDATES
    with pytest.raises(NotFound) as plain:
        require_chosen(decision)
    assert plain.value.details == {"kind": KIND.value, "key": KEY}
    with pytest.raises(NotFound) as missing:
        require_chosen(decision, missing_packs=("core",))
    assert missing.value.details["kind"] == "pack_version"
    assert missing.value.details["pack"] == "core"


def test_digest_pin_selects_the_matching_candidate_even_of_a_weaker_pack() -> None:
    high, low = installed("high", priority=10), installed("low", priority=1)
    versions = [version_in(high, digest="1"), version_in(low, digest="2")]
    choices = [choice_of(high), choice_of(low)]
    pin = parse_resource_pin("sha256:" + "2" * 64)
    decision = resolve(KIND, KEY, choices, versions, frozenset(), pin)
    assert decision.chosen == versions[1]
    assert [row.reason for row in decision.candidates] == ["pin_mismatch", "chosen"]


def test_version_pin_and_unsatisfied_pin() -> None:
    row = installed()
    version = version_in(row, version="1.2.3")
    assert (
        resolve(KIND, KEY, [choice_of(row)], [version], frozenset(), parse_resource_pin("1.2.3")).chosen
        == version
    )
    decision = resolve(KIND, KEY, [choice_of(row)], [version], frozenset(), parse_resource_pin("9.9.9"))
    assert decision.outcome is ResolutionOutcome.PIN_UNSATISFIED
    with pytest.raises(NotFound) as refused:
        require_chosen(decision)
    assert refused.value.details["reason"] == "pin_unsatisfied"


def test_a_quarantined_pinned_candidate_is_not_replaced_by_another_digest() -> None:
    high, low = installed("high", priority=10), installed("low", priority=1)
    versions = [version_in(high, digest="1"), version_in(low, digest="2")]
    decision = resolve(
        KIND,
        KEY,
        [choice_of(high), choice_of(low)],
        versions,
        frozenset({versions[0].id}),
        parse_resource_pin("sha256:" + "1" * 64),
    )
    assert decision.chosen is None
    assert decision.outcome is ResolutionOutcome.QUARANTINED


def test_versions_outside_the_chosen_pack_versions_never_compete() -> None:
    chosen, other = installed("core", "1.0.0"), installed("core", "2.0.0")
    versions = [version_in(chosen, digest="1"), version_in(other, digest="2")]
    assert resolve(KIND, KEY, [choice_of(chosen)], versions, frozenset(), None).chosen == versions[0]


# ---------------------------------------------------------------------------------------- PackPins (K19)
def test_pins_choose_exactly_the_pinned_version_when_a_newer_one_is_installed() -> None:
    old, new = installed("core", "1.0.0"), installed("core", "2.0.0")
    latest, _ = choose_pack_versions(["core"], {}, [old, new])
    assert latest[0].version_id == new.version_id  # the negative example: without pins the update is taken
    pinned = choices_from_pins({"core": old.version_id}, [old, new])
    assert [item.version_id for item in pinned] == [old.version_id]


def test_pins_keep_a_pack_that_is_no_longer_enabled_and_add_nothing_else() -> None:
    disabled, enabled_now = installed("extra", "1.0.0"), installed("core", "1.0.0")
    pinned = choices_from_pins({"extra": disabled.version_id}, [disabled, enabled_now])
    assert [item.slug for item in pinned] == ["extra"]


@pytest.mark.parametrize("state", [PackState.RETIRED])
def test_a_retired_pinned_version_is_pinned_pack_missing(state: PackState) -> None:
    gone = installed(state=state)
    with pytest.raises(NotFound) as refused:
        choices_from_pins({"core": gone.version_id}, [gone, installed(version="2.0.0")])
    assert refused.value.details["reason"] == "pinned_pack_missing"
    assert refused.value.details["pack"] == "core"


def test_an_unknown_pinned_version_or_the_version_of_another_pack_is_pinned_pack_missing() -> None:
    foreign = installed("other-pack")
    for version_id in (PackVersionId(uuid4()), foreign.version_id):
        with pytest.raises(NotFound) as refused:
            choices_from_pins({"core": version_id}, [foreign])
        assert refused.value.details["reason"] == "pinned_pack_missing"


def test_a_pinned_quarantined_resource_is_not_replaced_by_another_version() -> None:
    old, new = installed("core", "1.0.0"), installed("core", "2.0.0")
    versions = [version_in(old, digest="1"), version_in(new, digest="2")]
    choices = choices_from_pins({"core": old.version_id}, [old, new])
    decision = resolve(KIND, KEY, choices, versions, frozenset({versions[0].id}), None)
    assert decision.chosen is None
    assert decision.outcome is ResolutionOutcome.QUARANTINED


def test_configured_priority_applies_under_pins_too() -> None:
    row = replace(installed(), priority=1)
    assert choices_from_pins({"core": row.version_id}, [row], priorities={"core": 9})[0].priority == 9
