"""An equal digest is no proof of equal files: one contract over memory ∥ PostgreSQL (extensions §4.14, §7.1).

The normative resource digest has no length framing, so two valid skills hash alike. A replay compares what is
stored, in its transaction: other files are ``EXTENSION_DIGEST_CONFLICT``, equal files ``already_installed``,
and what cannot be compared is refused. A pair never holds other files under a digest it has, so a pin by
digest keeps naming one content. PostgreSQL also proves that the bytes round trip through ``bytea``.
"""

from typing import Any, Final

import pytest

from contracts.extensions.harness import ACTOR, NOW, FakeEstimator, Side, build_world, pack_payload
from fakes.clock import FrozenClock
from skm.adapters.memory.extensions.mapping import extensions_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, Conflict
from skm.kernel.ids import ResourceVersionId
from skm.modules.extensions.application.candidate import PackCandidate, build_candidate
from skm.modules.extensions.application.install import install_candidate
from skm.modules.extensions.domain.keys import PackId, PackVersionId
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import BUILTIN_ORIGIN, Pack, PackState, PackTrust, PackVersion
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated.results import InstallPackResult
from skm.modules.extensions.ports import PackRepository, ResourceRepository

SKILL_MANIFEST: Final = 'schema = "urn:skm:extensions:skill-manifest:v1"\nkey = "review"\nversion = "1.0.0"\n'
SKILL: Final = {
    "skills/review/SKILL.md": b"# Review\n",
    "skills/review/manifest.toml": SKILL_MANIFEST.encode(),
}
FIRST: Final = "skills/review/references/a.md"
SECOND: Final = "skills/review/references/b/two.md"
TWO_FILES: Final = {**SKILL, FIRST: b"1", SECOND: b"2"}
ONE_FILE: Final = {**SKILL, FIRST: b"1references/b/two.md\x002"}


@pytest.fixture(scope="module")
def config() -> Any:
    world = build_world()
    with world.uow() as uow:
        return world.config(uow)


def _candidate(binary: dict[str, bytes], version: str = "1.0.0", slug: str = "core") -> PackCandidate:
    return build_candidate(pack_payload(slug, version, binary=binary), estimator=FakeEstimator())


def _install(
    side: Side, config: Any, candidate: PackCandidate, *, dry_run: bool = False
) -> InstallPackResult:
    with side.uow() as uow:
        result = install_candidate(
            candidate,
            origin=BUILTIN_ORIGIN,
            trust=PackTrust.BUILTIN,
            installed_by=ACTOR,
            clock=FrozenClock(NOW),
            ids=side.ids,
            config=config,
            uow=uow,
            dry_run=dry_run,
        )
        uow.commit()
    return result


def _rows(side: Side) -> tuple[Any, ...]:
    with side.uow(readonly=True) as uow:
        versions = uow.repo(PackRepository).list_versions()
        rows = uow.repo(ResourceRepository).list_in_pack_versions(
            [row.version_id for row in versions], kind=None
        )
    return (*(row.version_id for row in versions), *(row.id for row in rows))


def _bodies(side: Side, version_id: ResourceVersionId) -> dict[str, bytes]:
    with side.uow(readonly=True) as uow:
        bodies = uow.repo(ResourceRepository).get_version(version_id, include_bodies=True).bodies
    assert bodies is not None
    return dict(bodies)


def _skill_version(side: Side) -> ResourceVersionId:
    with side.uow(readonly=True) as uow:
        versions = uow.repo(PackRepository).list_versions()
        rows = uow.repo(ResourceRepository).versions_of(
            ResourceKind.SKILL, "review", [row.version_id for row in versions]
        )
    return rows[0].id


def test_the_two_layouts_are_valid_and_collide() -> None:
    """The reproducer: both pass every check of a candidate, and the normative digest cannot tell them."""
    one, two = _candidate(ONE_FILE), _candidate(TWO_FILES)
    assert one.resources[0].bodies != two.resources[0].bodies
    assert one.resources[0].digest == two.resources[0].digest
    assert one.digest == two.digest


@pytest.mark.parametrize(("stored", "offered"), [(TWO_FILES, ONE_FILE), (ONE_FILE, TWO_FILES)])
def test_a_replay_with_other_files_under_the_digest_is_a_conflict(
    side: Side, config: Any, stored: dict[str, bytes], offered: dict[str, bytes]
) -> None:
    first = _install(side, config, _candidate(stored))
    before = _rows(side)
    with pytest.raises(Conflict) as refused:
        _install(side, config, _candidate(offered))
    assert refused.value.code is ErrorCode.EXTENSION_DIGEST_CONFLICT
    assert refused.value.details["reason"] == "digest_collision"
    assert refused.value.details["installed"] == refused.value.details["offered"] == first.digest
    assert refused.value.details["resources"] == [{"kind": "skill", "key": "review"}]
    assert _rows(side) == before
    assert _bodies(side, _skill_version(side)) == _candidate(stored).resources[0].bodies


def test_a_dry_run_replay_is_refused_too(side: Side, config: Any) -> None:
    _install(side, config, _candidate(TWO_FILES))
    with pytest.raises(Conflict):
        _install(side, config, _candidate(ONE_FILE), dry_run=True)


def test_a_replay_with_the_same_files_is_already_installed(side: Side, config: Any) -> None:
    first = _install(side, config, _candidate(TWO_FILES))
    before = _rows(side)
    again = _install(side, config, _candidate(TWO_FILES))
    assert (first.status, again.status) == ("installed", "already_installed")
    assert again.pack_version_id == first.pack_version_id
    assert _rows(side) == before
    assert _bodies(side, _skill_version(side)) == {
        "SKILL.md": b"# Review\n",
        "manifest.toml": SKILL_MANIFEST.encode(),
        "references/a.md": b"1",
        "references/b/two.md": b"2",
    }


def _store_without_resources(side: Side, candidate: PackCandidate) -> None:
    pack_id = PackId(side.ids.new_id())
    with side.uow() as uow:
        packs = uow.repo(PackRepository)
        packs.add(Pack(pack_id, candidate.manifest.slug, "Core", "skm", PackTrust.BUILTIN, NOW))
        packs.add_version(
            PackVersion(
                id=PackVersionId(side.ids.new_id()),
                pack_id=pack_id,
                version=candidate.manifest.version,
                digest=candidate.digest,
                manifest=candidate.manifest,
                state=PackState.ACTIVE,
                origin=BUILTIN_ORIGIN,
                installed_at=NOW,
                installed_by=ACTOR,
            )
        )
        uow.commit()


def _lose_every_file(side: Side, version_id: ResourceVersionId) -> None:
    if side.pg is not None:
        side.pg.execute("TRUNCATE skm_extensions.resource_files")
        return
    assert side.memory is not None
    del extensions_state(side.memory.committed).bodies[version_id]


def _lose_one_file(side: Side, version_id: ResourceVersionId) -> None:
    if side.pg is not None:
        side.pg.execute(
            "ALTER TABLE skm_extensions.resource_files DISABLE TRIGGER tg_resource_files__immutable"
        )
        try:
            side.pg.execute(
                "DELETE FROM skm_extensions.resource_files WHERE resource_version_id = %s AND path = %s",
                (version_id, "references/b/two.md"),
            )
        finally:
            side.pg.execute(
                "ALTER TABLE skm_extensions.resource_files ENABLE TRIGGER tg_resource_files__immutable"
            )
        return
    assert side.memory is not None
    del extensions_state(side.memory.committed).bodies[version_id]["references/b/two.md"]


def test_a_replay_without_stored_resources_fails_closed(side: Side, config: Any) -> None:
    candidate = _candidate(TWO_FILES)
    _store_without_resources(side, candidate)
    with pytest.raises(CapabilityUnavailable) as refused:
        _install(side, config, candidate)
    assert refused.value.details == {
        "reason": "stored_evidence_unavailable",
        "resources": [{"kind": "skill", "key": "review"}],
    }


@pytest.mark.parametrize("lose", [_lose_every_file, _lose_one_file])
def test_a_replay_without_stored_files_fails_closed(side: Side, config: Any, lose: Any) -> None:
    _install(side, config, _candidate(TWO_FILES))
    lose(side, _skill_version(side))
    with pytest.raises(CapabilityUnavailable) as refused:
        _install(side, config, _candidate(TWO_FILES))
    assert refused.value.details["reason"] == "stored_evidence_unavailable"


def test_a_new_version_cannot_bring_other_files_under_a_digest_of_the_pair(side: Side, config: Any) -> None:
    """Otherwise a pin by digest, which takes any version of the pair, would reach the other files."""
    _install(side, config, _candidate(TWO_FILES))
    before = _rows(side)
    with pytest.raises(Conflict) as refused:
        _install(side, config, _candidate(ONE_FILE, "1.1.0"))
    assert refused.value.code is ErrorCode.EXTENSION_DIGEST_CONFLICT
    assert refused.value.details["reason"] == "digest_collision"
    assert refused.value.details["resources"] == [{"kind": "skill", "key": "review"}]
    assert _rows(side) == before


def test_a_new_version_may_bring_the_same_files(side: Side, config: Any) -> None:
    """The negative example of the rule above: the same content may arrive in two versions of a pack."""
    first = _install(side, config, _candidate(TWO_FILES))
    second = _install(side, config, _candidate(TWO_FILES, "1.1.0"))
    assert second.status == "installed"
    assert second.resources[0].digest == first.resources[0].digest


def test_a_new_version_over_lost_files_fails_closed(side: Side, config: Any) -> None:
    _install(side, config, _candidate(TWO_FILES))
    _lose_every_file(side, _skill_version(side))
    with pytest.raises(CapabilityUnavailable) as refused:
        _install(side, config, _candidate(ONE_FILE, "1.1.0"))
    assert refused.value.details["reason"] == "stored_evidence_unavailable"


def _payload_with_config(value: str) -> PackPayload:
    return pack_payload(extra_manifest=f'[config]\n"context.ratio" = {value}\n')


def test_a_replay_with_another_manifest_under_the_digest_is_a_conflict(side: Side, config: Any) -> None:
    """``pack_digest`` takes a float as its ``repr``: ``0.5`` and ``"0.5"`` are one digest, two manifests."""
    stored = build_candidate(_payload_with_config('"0.5"'), estimator=FakeEstimator())
    offered = build_candidate(_payload_with_config("0.5"), estimator=FakeEstimator())
    assert stored.digest == offered.digest
    assert stored.manifest != offered.manifest
    _store_without_resources(side, stored)
    with pytest.raises(Conflict) as refused:
        _install(side, config, offered)
    assert refused.value.details["reason"] == "digest_collision"
    assert refused.value.details["resources"] == []
    assert _install(side, config, stored).status == "already_installed"
