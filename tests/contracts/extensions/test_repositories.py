"""Pack, resource and quarantine repositories: one contract over memory ∥ PostgreSQL (extensions §6, §11).

memory ∥ pg: versions round trip with manifest and files; bodies only on request; the newest-first listing and
the domain order agree; unique pairs refuse a second row; metadata must describe its bytes; one active
quarantine row per version, the released row stays as history; state only retires. PostgreSQL only: the
immutability triggers of ``0018``.
"""

from dataclasses import replace
from typing import Any

import psycopg
import pytest

from contracts.extensions.harness import ACTOR, NOW, OTHER_ACTOR, Side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, PreconditionFailed
from skm.kernel.ids import ResourceVersionId
from skm.modules.extensions.domain.compat import (
    CompatCheck,
    CompatCheckId,
    CompatReport,
    CompatStatus,
    CompatVerdict,
)
from skm.modules.extensions.domain.digest_rules import file_digest, resource_digest
from skm.modules.extensions.domain.keys import PackId, PackVersionId, ResourceId, SemVer, VersionConstraint
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import (
    Pack,
    PackManifest,
    PackState,
    PackTrust,
    PackVersion,
)
from skm.modules.extensions.domain.quarantine import QuarantineEntry
from skm.modules.extensions.domain.resource import Resource, ResourceFile, ResourceVersion
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

BODY = b"+++\nschema = 1\n+++\nbody\n"


def packs(uow: Any) -> PackRepository:
    return uow.repo(PackRepository)


def resources(uow: Any) -> ResourceRepository:
    return uow.repo(ResourceRepository)


def quarantine(uow: Any) -> QuarantineRepository:
    return uow.repo(QuarantineRepository)


def _manifest(version: str = "1.0.0", slug: str = "core") -> PackManifest:
    return PackManifest(
        slug=slug,
        version=SemVer.parse(version),
        title="Core",
        description="Core pack",
        publisher="skm",
        trust=PackTrust.BUILTIN,
        priority=0,
        license="Apache-2.0",
        requires_skm=VersionConstraint.parse(">=2.0.0,<3"),
        config={"context.max_total_tokens": 1000},
        exclusive_groups=(),
        overrides=(),
    )


def _pack(side: Side, slug: str = "core") -> Pack:
    pack = Pack(PackId(side.ids.new_id()), slug, "Core", "skm", PackTrust.BUILTIN, NOW)
    with side.uow() as uow:
        packs(uow).add(pack)
        uow.commit()
    return pack


def _version(side: Side, pack: Pack, version: str = "1.0.0") -> PackVersion:
    row = PackVersion(
        id=PackVersionId(side.ids.new_id()),
        pack_id=pack.id,
        version=SemVer.parse(version),
        digest="sha256:" + "a" * 64,
        manifest=_manifest(version, pack.slug),
        state=PackState.ACTIVE,
        origin="builtin",
        installed_at=NOW,
        installed_by=ACTOR,
    )
    with side.uow() as uow:
        packs(uow).add_version(row)
        uow.commit()
    return row


def _resource(side: Side, pack: Pack, key: str = "executor") -> Resource:
    row = Resource(ResourceId(side.ids.new_id()), ResourceKind.AGENT_PROFILE, key, pack.id, NOW)
    with side.uow() as uow:
        resources(uow).add(row)
        uow.commit()
    return row


def _resource_version(
    side: Side, resource: Resource, pack_version: PackVersion, body: bytes = BODY
) -> ResourceVersion:
    file = ResourceFile("executor.toml", len(body), file_digest(body), "application/toml")
    row = ResourceVersion(
        id=ResourceVersionId(side.ids.new_id()),
        resource_id=resource.id,
        kind=resource.kind,
        key=resource.key,
        pack_version_id=pack_version.id,
        version=pack_version.version,
        digest=resource_digest({file.path: body}),
        manifest={"role": "executor", "nested": {"a": [1, "é", None]}},
        files=(file,),
        tokens_estimate=3,
        compat=CompatReport((CompatCheck(CompatCheckId.LAYOUT, CompatStatus.OK, "ok"),), CompatVerdict.CLEAN),
        created_at=NOW,
    )
    with side.uow() as uow:
        resources(uow).add_version(row, {file.path: body})
        uow.commit()
    return row


def test_pack_version_round_trip_keeps_manifest_and_identity(side: Side) -> None:
    pack = _pack(side)
    stored = _version(side, pack, "1.2.3-rc.1")
    with side.uow(readonly=True) as uow:
        assert packs(uow).get(pack.id) == pack
        assert packs(uow).find_by_slug("core") == pack
        assert packs(uow).find_by_slug("absent") is None
        assert packs(uow).get_version(stored.id) == stored
        assert packs(uow).find_version(pack.id, SemVer.parse("1.2.3-rc.1")) == stored
        assert packs(uow).find_version(pack.id, SemVer.parse("9.9.9")) is None
        with pytest.raises(NotFound) as missing:
            packs(uow).get_version(PackVersionId(side.ids.new_id()))
    assert missing.value.details["kind"] == "pack_version"


def test_unique_slug_and_version_refuse_a_second_row(side: Side) -> None:
    pack = _pack(side)
    stored = _version(side, pack)
    with side.uow() as uow, pytest.raises(Conflict) as twin:
        packs(uow).add(Pack(PackId(side.ids.new_id()), "core", "Other", "skm", PackTrust.BUILTIN, NOW))
    assert twin.value.code is ErrorCode.ALREADY_EXISTS
    with side.uow() as uow, pytest.raises(Conflict) as again:
        packs(uow).add_version(replace(stored, id=PackVersionId(side.ids.new_id())))
    assert again.value.code is ErrorCode.ALREADY_EXISTS


def test_list_versions_filters_by_pack_and_state(side: Side) -> None:
    core, other = _pack(side), _pack(side, "other-pack")
    old, new = _version(side, core, "1.9.0"), _version(side, core, "1.10.0")
    _version(side, other, "1.0.0")
    with side.uow() as uow:
        packs(uow).set_version_state(old.id, PackState.RETIRED)
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert {row.version_id for row in packs(uow).list_versions(core.id)} == {old.id, new.id}
        active = packs(uow).list_versions(core.id, state=PackState.ACTIVE)
        everything = packs(uow).list_versions()
    assert [row.version_id for row in active] == [new.id]
    assert active[0].slug == "core"
    assert active[0].trust is PackTrust.BUILTIN
    assert active[0].priority == 0
    assert len(everything) == 3


def test_state_only_retires(side: Side) -> None:
    stored = _version(side, _pack(side))
    with side.uow() as uow:
        packs(uow).set_version_state(stored.id, PackState.RETIRED)
        uow.commit()
    with side.uow() as uow, pytest.raises(PreconditionFailed) as back:
        packs(uow).set_version_state(stored.id, PackState.ACTIVE)
    assert back.value.code is ErrorCode.INVALID_TRANSITION
    with side.uow() as uow, pytest.raises(NotFound):
        packs(uow).set_version_state(PackVersionId(side.ids.new_id()), PackState.RETIRED)


def test_resource_version_round_trip_and_bodies_only_on_request(side: Side) -> None:
    pack = _pack(side)
    version = _version(side, pack)
    resource = _resource(side, pack)
    stored = _resource_version(side, resource, version)
    with side.uow(readonly=True) as uow:
        assert resources(uow).find(ResourceKind.AGENT_PROFILE, "executor") == resource
        assert resources(uow).find(ResourceKind.SKILL, "executor") is None
        assert resources(uow).owner_trust(ResourceKind.AGENT_PROFILE, "executor") is PackTrust.BUILTIN
        assert resources(uow).owner_trust(ResourceKind.SKILL, "absent") is None
        plain = resources(uow).get_version(stored.id)
        full = resources(uow).get_version(stored.id, include_bodies=True)
        summaries = resources(uow).versions_of(ResourceKind.AGENT_PROFILE, "executor", [version.id])
        listed = resources(uow).list_in_pack_versions([version.id], kind=None)
        of_kind = resources(uow).list_in_pack_versions([version.id], kind=ResourceKind.SKILL)
    assert plain.version == stored
    assert plain.bodies is None
    assert full.bodies == {"executor.toml": BODY}
    assert [row.id for row in summaries] == [stored.id] == [row.id for row in listed]
    assert summaries[0].digest == stored.digest
    assert summaries[0].verdict is CompatVerdict.CLEAN
    assert of_kind == ()


def test_metadata_that_does_not_describe_its_bytes_is_refused(side: Side) -> None:
    pack = _pack(side)
    version = _version(side, pack)
    resource = _resource(side, pack)
    file = ResourceFile("executor.toml", len(BODY), file_digest(b"other bytes"), "application/toml")
    row = ResourceVersion(
        id=ResourceVersionId(side.ids.new_id()),
        resource_id=resource.id,
        kind=resource.kind,
        key=resource.key,
        pack_version_id=version.id,
        version=version.version,
        digest="sha256:" + "b" * 64,
        manifest={},
        files=(file,),
        tokens_estimate=0,
        compat=CompatReport((), CompatVerdict.CLEAN),
        created_at=NOW,
    )
    with side.uow() as uow, pytest.raises(InternalError):
        resources(uow).add_version(row, {"executor.toml": BODY})


def test_one_version_of_a_resource_per_pack_version(side: Side) -> None:
    pack = _pack(side)
    version = _version(side, pack)
    resource = _resource(side, pack)
    stored = _resource_version(side, resource, version)
    with side.uow() as uow, pytest.raises(Conflict) as twin:
        resources(uow).add_version(
            replace(stored, id=ResourceVersionId(side.ids.new_id())), {"executor.toml": BODY}
        )
    assert twin.value.code is ErrorCode.ALREADY_EXISTS


def test_quarantine_one_active_row_and_history_on_release(side: Side) -> None:
    pack = _pack(side)
    version = _version(side, pack)
    stored = _resource_version(side, _resource(side, pack), version)
    entry = QuarantineEntry(stored.id, "manual reason", {}, ACTOR, NOW)
    with side.uow() as uow:
        quarantine(uow).add(entry)
        uow.commit()
    with side.uow() as uow:
        assert quarantine(uow).quarantined_ids([stored.id]) == frozenset({stored.id})
        with pytest.raises(Conflict) as twin:
            quarantine(uow).add(entry)
    assert twin.value.code is ErrorCode.ALREADY_EXISTS
    with side.uow() as uow:
        quarantine(uow).release(stored.id, by=OTHER_ACTOR, reason="fixed", at=NOW)
        uow.commit()
    with side.uow() as uow:
        assert quarantine(uow).quarantined_ids([stored.id]) == frozenset()
        with pytest.raises(PreconditionFailed) as twice:
            quarantine(uow).release(stored.id, by=OTHER_ACTOR, reason="again", at=NOW)
    assert twice.value.code is ErrorCode.INVALID_TRANSITION
    with side.uow() as uow:  # the released row stays history and a new quarantine is possible
        quarantine(uow).add(QuarantineEntry(stored.id, "compat", {"reasons": ["license"]}, ACTOR, NOW))
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert quarantine(uow).quarantined_ids([stored.id]) == frozenset({stored.id})


def test_the_registry_lock_can_be_taken_again_in_one_unit_of_work(side: Side) -> None:
    with side.uow() as uow:
        packs(uow).lock_registry()
        packs(uow).lock_registry()  # a sync installs several packs in one transaction
        uow.commit()


def test_a_rolled_back_unit_of_work_leaves_nothing(side: Side) -> None:
    pack = Pack(PackId(side.ids.new_id()), "core", "Core", "skm", PackTrust.BUILTIN, NOW)
    with side.uow() as uow:
        packs(uow).add(pack)  # no commit
    with side.uow(readonly=True) as uow:
        assert packs(uow).find_by_slug("core") is None


@pytest.mark.pg
def test_postgres_triggers_keep_every_version_immutable(side: Side) -> None:
    if side.pg is None:
        pytest.skip("the triggers of 0018 exist only in PostgreSQL")
    pack = _pack(side)
    version = _version(side, pack)
    stored = _resource_version(side, _resource(side, pack), version)
    digest = "sha256:" + "f" * 64
    for statement, params in (
        ("UPDATE skm_extensions.packs SET title = 'x' WHERE id = %s", (pack.id,)),
        ("UPDATE skm_extensions.pack_versions SET digest = %s WHERE id = %s", (digest, version.id)),
        ("UPDATE skm_extensions.resource_versions SET tokens_estimate = 9 WHERE id = %s", (stored.id,)),
        (
            "UPDATE skm_extensions.resource_files SET media_type = 'x' WHERE resource_version_id = %s",
            (stored.id,),
        ),
        ("DELETE FROM skm_extensions.resource_files WHERE resource_version_id = %s", (stored.id,)),
    ):
        with pytest.raises(psycopg.errors.RestrictViolation, match=r"(?i)(immutable|only state)"):
            side.pg.execute(statement, params)
