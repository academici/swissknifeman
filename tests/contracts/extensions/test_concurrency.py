"""Registry writers on two PostgreSQL connections, in the isolation of their commands (extensions §7.1, §7.5).

The first writer stays open until the second is seen waiting for the registry lock, so the second cannot read
before the first commits. Retiring the two last active versions of ``core`` leaves one; installing one version
twice is ``already_installed`` with the same digest and ``EXTENSION_DIGEST_CONFLICT`` with another, or with
other files under the same digest; an external pack behind a writer is still refused without a scan. The trust
of an override is read through the real queries.
"""

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, Final

import pytest

from contracts.extensions.harness import (
    ACTOR,
    NOW,
    FakeEstimator,
    Side,
    build_world,
    pack_payload,
    postgres_side,
)
from fakes.clock import FrozenClock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, Conflict, Forbidden, SkmError
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.modules.extensions.application import candidate as candidate_module
from skm.modules.extensions.application.candidate import build_candidate
from skm.modules.extensions.application.commands import install_pack, uninstall_pack_version
from skm.modules.extensions.application.install import install_candidate
from skm.modules.extensions.domain.compat import (
    CompatCheck,
    CompatCheckId,
    CompatReport,
    CompatStatus,
    CompatVerdict,
)
from skm.modules.extensions.domain.pack import BUILTIN_ORIGIN, PackState, PackTrust
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated.commands import UninstallPackVersion
from skm.modules.extensions.generated.results import InstallPackResult
from skm.modules.extensions.ports import PackRepository
from support.pg import TestDatabase

pytestmark = pytest.mark.pg

WAITERS: Final = "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
WAIT_SECONDS: Final = 5.0

type Step = Callable[[UnitOfWork], object]


@pytest.fixture
def pg_side(clean_test_database: TestDatabase) -> Iterator[Side]:
    made = postgres_side(clean_test_database)
    try:
        yield made
    finally:
        made.close()


@pytest.fixture(scope="module")
def config() -> Any:
    world = build_world()
    with world.uow() as uow:
        return world.config(uow)


def _unit(side: Side, name: str, isolation: Any) -> UnitOfWork:
    meta = RequestMeta(f"req_{name:0>26}", Surface.TEST, None, NOW)
    return side.uow_factory(meta, isolation=isolation)


def _waiting(side: Side) -> bool:
    assert side.pg is not None
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if side.pg.execute(WAITERS)[0][0] > 0:
            return True
        time.sleep(0.01)
    return False


def _race(side: Side, isolation: Any, first: Step, second: Step) -> tuple[object, object]:
    """``first`` holds its transaction open until ``second`` waits for the lock, then both finish."""
    outcome: list[object] = []

    def later() -> None:
        try:
            with _unit(side, "second", isolation) as uow:
                result = second(uow)
                uow.commit()
            outcome.append(result)
        except SkmError as exc:
            outcome.append(exc)

    thread = threading.Thread(target=later)
    with _unit(side, "first", isolation) as uow:
        winner = first(uow)
        thread.start()
        blocked = _waiting(side)
        uow.commit()
    thread.join(WAIT_SECONDS)
    assert not thread.is_alive()
    assert blocked, "the second writer never waited for the registry lock"
    return winner, outcome[0]


def _install(side: Side, config: Any, payload: PackPayload) -> Step:
    candidate = build_candidate(payload, estimator=FakeEstimator())

    def step(uow: UnitOfWork) -> InstallPackResult:
        return install_candidate(
            candidate,
            origin=BUILTIN_ORIGIN,
            trust=PackTrust.BUILTIN,
            installed_by=ACTOR,
            clock=FrozenClock(NOW),
            ids=side.ids,
            config=config,
            uow=uow,
        )

    return step


def _install_external(
    side: Side, config: Any, payload: PackPayload, trust: PackTrust, *, scan: bool = True
) -> Callable[[UnitOfWork], InstallPackResult]:
    candidate = build_candidate(payload, estimator=FakeEstimator(), scan=scan)

    def step(uow: UnitOfWork) -> InstallPackResult:
        return install_candidate(
            candidate,
            origin="path:/packs/x",
            trust=trust,
            installed_by=ACTOR,
            clock=FrozenClock(NOW),
            ids=side.ids,
            config=config,
            uow=uow,
        )

    return step


def _prompt(text: str, version: str = "1.0.0") -> PackPayload:
    return pack_payload(version=version, files={"prompts/shared/x.md": text})


def _committed(side: Side) -> tuple[tuple[str, str], ...]:
    with side.uow(readonly=True) as uow:
        rows = uow.repo(PackRepository).list_versions()
    return tuple((str(row.version), row.state.value) for row in rows)


def test_concurrent_retirements_keep_the_last_active_core_version(pg_side: Side, config: Any) -> None:
    for version in ("1.0.0", "1.1.0"):
        with pg_side.uow() as uow:
            _install(pg_side, config, _prompt("x", version))(uow)
            uow.commit()
    with pg_side.uow(readonly=True) as uow:
        first_id, second_id = (row.version_id for row in uow.repo(PackRepository).list_versions())

    def retire(version_id: Any) -> Step:
        def step(uow: UnitOfWork) -> object:
            return uninstall_pack_version.handle(UninstallPackVersion(pack_version_id=version_id), None, uow)  # type: ignore[arg-type]

        return step

    winner, loser = _race(pg_side, uninstall_pack_version.SPEC.isolation, retire(first_id), retire(second_id))
    assert getattr(winner, "state", None) == "retired"
    assert isinstance(loser, Forbidden)
    assert loser.details["reason"] == "last_core_version"
    states = [state for _version, state in _committed(pg_side)]
    assert sorted(states) == [PackState.ACTIVE.value, PackState.RETIRED.value]


def test_concurrent_retirements_of_one_version_are_one_transition(pg_side: Side, config: Any) -> None:
    for version in ("1.0.0", "1.1.0"):
        with pg_side.uow() as uow:
            _install(pg_side, config, _prompt("x", version))(uow)
            uow.commit()
    with pg_side.uow(readonly=True) as uow:
        target = uow.repo(PackRepository).list_versions()[0].version_id

    def retire(uow: UnitOfWork) -> object:
        return uninstall_pack_version.handle(UninstallPackVersion(pack_version_id=target), None, uow)  # type: ignore[arg-type]

    _winner, loser = _race(pg_side, uninstall_pack_version.SPEC.isolation, retire, retire)
    assert isinstance(loser, SkmError)
    assert loser.code is ErrorCode.INVALID_TRANSITION


def test_concurrent_installs_of_the_same_digest_are_already_installed(pg_side: Side, config: Any) -> None:
    step = _install(pg_side, config, _prompt("same"))
    winner, loser = _race(pg_side, install_pack.SPEC.isolation, step, step)
    assert isinstance(winner, InstallPackResult)
    assert isinstance(loser, InstallPackResult)
    assert (winner.status, loser.status) == ("installed", "already_installed")
    assert winner.pack_version_id == loser.pack_version_id
    assert winner.digest == loser.digest
    assert _committed(pg_side) == (("1.0.0", "active"),)


def test_concurrent_installs_of_another_digest_are_a_conflict(pg_side: Side, config: Any) -> None:
    winner, loser = _race(
        pg_side,
        install_pack.SPEC.isolation,
        _install(pg_side, config, _prompt("one")),
        _install(pg_side, config, _prompt("other")),
    )
    assert isinstance(winner, InstallPackResult)
    assert winner.status == "installed"
    assert isinstance(loser, Conflict)
    assert loser.code is ErrorCode.EXTENSION_DIGEST_CONFLICT
    assert loser.details["installed"] == winner.digest
    assert _committed(pg_side) == (("1.0.0", "active"),)


def test_concurrent_installs_of_colliding_files_are_a_conflict(pg_side: Side, config: Any) -> None:
    """Same digest, other files: the second writer waits, then compares what the first one committed."""
    skill = {
        "skills/review/SKILL.md": b"# Review\n",
        "skills/review/manifest.toml": (
            b'schema = "urn:skm:extensions:skill-manifest:v1"\nkey = "review"\nversion = "1.0.0"\n'
        ),
    }
    one = {**skill, "skills/review/references/a.md": b"1references/b/two.md\x002"}
    two = {**skill, "skills/review/references/a.md": b"1", "skills/review/references/b/two.md": b"2"}
    winner, loser = _race(
        pg_side,
        install_pack.SPEC.isolation,
        _install(pg_side, config, pack_payload(binary=one)),
        _install(pg_side, config, pack_payload(binary=two)),
    )
    assert isinstance(winner, InstallPackResult)
    assert winner.status == "installed"
    assert isinstance(loser, Conflict)
    assert loser.code is ErrorCode.EXTENSION_DIGEST_CONFLICT
    assert loser.details["reason"] == "digest_collision"
    assert loser.details["installed"] == loser.details["offered"] == winner.digest
    assert _committed(pg_side) == (("1.0.0", "active"),)


@pytest.mark.parametrize("trust", [PackTrust.OPERATOR, PackTrust.THIRD_PARTY])
def test_an_unscanned_external_install_behind_a_writer_commits_nothing(
    pg_side: Side, config: Any, trust: PackTrust
) -> None:
    payload = pack_payload("extra", trust=trust.value, files={"prompts/extra/note.md": "x"})
    winner, loser = _race(
        pg_side,
        install_pack.SPEC.isolation,
        _install(pg_side, config, _prompt("one")),
        _install_external(pg_side, config, payload, trust, scan=False),
    )
    assert isinstance(winner, InstallPackResult)
    assert isinstance(loser, CapabilityUnavailable)
    assert loser.details["reason"] == "compat_scanner_unavailable"
    assert _committed(pg_side) == (("1.0.0", "active"),)


def test_override_trust_counts_every_holder_on_postgres(
    pg_side: Side, config: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real query behind §4.13: a third party that came first does not lower the bar under an operator."""
    scanned = CompatReport(
        tuple(CompatCheck(check, CompatStatus.OK, "seen") for check in CompatCheckId), CompatVerdict.CLEAN
    )
    monkeypatch.setattr(candidate_module, "_layout_report", lambda: scanned)
    files = {"prompts/shared/note.md": "x"}
    declared = '[[overrides]]\nkind = "prompt_block"\nkey = "shared/note"\nreason = "mine"\n'
    first = pack_payload("first-pack", trust="third_party", files=files)
    second = pack_payload("site-pack", trust="operator", files=files, extra_manifest=declared)
    later = pack_payload("later-pack", trust="third_party", files=files, extra_manifest=declared)
    with pg_side.uow() as uow:
        _install_external(pg_side, config, first, PackTrust.THIRD_PARTY)(uow)
        uow.commit()
    with pg_side.uow() as uow:
        assert _install_external(pg_side, config, second, PackTrust.OPERATOR)(uow).resources[0].overrides
        uow.commit()
    with pg_side.uow() as uow, pytest.raises(Conflict) as refused:
        _install_external(pg_side, config, later, PackTrust.THIRD_PARTY)(uow)
    assert refused.value.code is ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED
    assert refused.value.details["owner_trust"] == "operator"
    assert len(_committed(pg_side)) == 2
