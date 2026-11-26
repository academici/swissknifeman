"""Machine HTTP isolation, pinned project dispatch and bounded retries through real ASGI routes."""

from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest

from fakes.clock import FrozenClock
from security.api.harness import BASE, NOW, TestClient, World, make_world
from skm.adapters.http_client.client import HttpSkmClient
from skm.application_bus.ports import IdempotencyStore
from skm.bootstrap.host_services import build_host_storage
from skm.bootstrap.machine_access import MachineAuthority, MachineCaller, MachineOperation, MachineProject
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.machine import _listen, create_machine_api
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ids import HostId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.workspace import public as workspace
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.machine import MachinePrincipal, MachineProfile, MachineSession, MachineStore

_MACHINE_URL = "http://skm-machine"
_PREFIX = "/api/v1/machine"
_SESSION = "SKM-Machine-Session"
_PROFILE = "SKM-Instance-Profile"
_TABLE = build_route_table(("access", "workspace"))
_REF = SecretRef.parse("secret://env/SKM_API_TOKEN")


class _Store:
    def __init__(self, instance: UUID, other_instance: UUID) -> None:
        self.installation = uuid4()
        self.sessions: dict[str, MachineSession] = {}
        self.settings: dict[tuple[MachinePrincipal, str], JsonValue] = {}
        self.profiles = {
            name: MachineProfile(
                self.installation,
                name,
                identity,
                f"https://{name}.invalid",
                f"https://{name}.invalid",
                credential_ref=_REF,
                revision=uuid4(),
            )
            for name, identity in (("first", instance), ("second", other_instance))
        }

    def get_installation_id(self) -> UUID:
        return self.installation

    def get_profile(self, installation: UUID, name: str) -> MachineProfile | None:
        return self.profiles.get(name) if installation == self.installation else None

    def put_session(self, session: MachineSession) -> bool:
        if self.profiles[session.profile.name] != session.profile:
            return False
        self.sessions[session.handle_hash] = session
        return True

    def get_session(self, installation: UUID, digest: str, now: datetime) -> MachinePrincipal | None:
        session = self.sessions.get(digest)
        if session is None or session.expires_at <= now:
            return None
        if self.get_profile(installation, session.profile.name) != session.profile:
            return None
        return MachinePrincipal(installation, session.profile.instance_id, session.principal_id)

    def delete_session(self, installation: UUID, digest: str) -> None:
        if installation == self.installation:
            self.sessions.pop(digest, None)

    def get_user_setting(self, scope: MachinePrincipal, key: str) -> JsonValue:
        return self.settings.get((scope, key))

    def set_user_setting(self, scope: MachinePrincipal, key: str, value: JsonValue) -> None:
        self.settings[scope, key] = value


def _http(tmp_path: Path, client: TestClient, token: str, instance: UUID) -> HttpSkmClient:
    return HttpSkmClient(
        BASE,
        SecretValue(_REF, token),
        _TABLE,
        spool_root=tmp_path / "spool",
        storage_budget=build_host_storage(tmp_path),
        min_free_bytes=0,
        http=client,
        expected_instance_id=instance,
        max_attempts=1,
    )


def _project_api(world: World):
    return create_app(world.core, route_table=_TABLE, registry=world.core.bus._registry, no_background=True)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _personal_token(world: World) -> str:
    client = world.core.client(actor=world.core.authenticate(world.secret), surface=Surface.TEST)
    person = cast(
        "Any",
        client.dispatch(
            access.CreatePrincipal.from_json({"kind": "human", "display_name": "Machine caller"})
        ),
    )
    issued = cast(
        "Any",
        client.dispatch(
            access.CreateToken(
                name="machine-caller", principal_id=person.principal_id, permissions=("token.own",)
            )
        ),
    )
    return str(issued.secret)


def test_machine_sessions_are_scoped_to_verified_person_and_instance(tmp_path: Path) -> None:  # noqa: PLR0915 -- one session lifecycle across project and machine boundaries
    world = make_world(tmp_path)
    second = uuid4()
    clock = FrozenClock(NOW)
    store = _Store(world.core.instance_id, second)
    used_tokens: list[str] = []
    down = False
    drop_after_admission = False

    with (
        TestClient(_project_api(world), base_url=BASE) as first_http,
        TestClient(
            _project_api(replace(world, core=replace(world.core, instance_id=second))), base_url=BASE
        ) as second_http,
    ):

        @contextmanager
        def connect(profile: MachineProfile, token: str) -> Generator[MachineProject]:
            used_tokens.append(token)
            if down:
                raise error_for(ErrorCode.BACKEND_UNAVAILABLE, "Project is offline", retryable=True)
            http = first_http if profile.name == "first" else second_http
            yield MachineProject(_http(tmp_path, http, token, profile.instance_id), HostId(uuid4()))

        created = first_http.post(
            "/api/v1/workspaces",
            json={"slug": "checkout-project", "title": "Checkout"},
            headers=world.headers,
        )
        assert created.status_code == 201, created.text
        workspace_id = created.json()["workspace_id"]

        def run_operation(
            operation: MachineOperation, caller: MachineCaller, payload: JsonObject, request_id: UUID | None
        ) -> JsonValue:
            assert operation == "repo.bind"
            assert request_id is not None

            def drop_upstream(_request: httpx.Request) -> None:
                raise httpx.ConnectError("synthetic disconnect after machine admission")

            if drop_after_admission:
                first_http.event_hooks["request"] = [drop_upstream]
            try:
                result = cast(
                    "workspace.WorkspaceView",
                    caller.client.ask(
                        workspace.GetWorkspace(
                            workspace_id=WorkspaceId(UUID(cast("str", payload["workspace_id"])))
                        )
                    ),
                )
            finally:
                first_http.event_hooks["request"] = []
            return {"workspace_id": str(result.workspace_id), "request_id": str(request_id)}

        authority = MachineAuthority(cast("MachineStore", store), store.installation, connect, clock=clock)
        api = create_machine_api(authority, default_profile="first", run_operation=run_operation)
        with TestClient(api, base_url=_MACHINE_URL, client=cast("tuple[str, int]", None)) as machine:
            user = _personal_token(world)
            accepted = machine.post(f"{_PREFIX}/session", headers=_bearer(world.secret))
            assert accepted.status_code == 201, accepted.text
            owner_handle = accepted.json()["handle"]
            assert owner_handle not in store.sessions
            person = machine.post(f"{_PREFIX}/session", headers=_bearer(user))
            assert person.status_code == 201, person.text
            person_handle = person.json()["handle"]
            same_user = machine.post(
                f"{_PREFIX}/session", headers={**_bearer(world.secret), _PROFILE: "second"}
            )
            assert same_user.status_code == 201, same_user.text
            other_handle = same_user.json()["handle"]
            setting = f"{_PREFIX}/settings/ui.theme"
            owner_session = {_SESSION: owner_handle}
            saved = machine.put(
                setting, json={"value": "dark"}, headers={**_bearer(world.secret), **owner_session}
            )
            assert saved.status_code == 200, saved.text
            assert (
                machine.put(
                    setting, json={"value": "light"}, headers={**_bearer(user), **owner_session}
                ).status_code
                == 403
            )
            assert machine.get(setting, headers={_SESSION: person_handle}).json()["value"] is None
            assert machine.get(setting, headers={_SESSION: other_handle}).json()["value"] is None
            assert (
                machine.get(f"{_PREFIX}/settings/runtimes.accounts", headers=owner_session).status_code == 404
            )
            assert (
                machine.get(
                    f"{_PREFIX}/instance/status", headers={"Origin": "https://elsewhere.invalid"}
                ).status_code
                == 403
            )
            assert machine.post(f"{_PREFIX}/dispatch", json={}).status_code == 404

            checkout = f"{_PREFIX}/repo/bind"
            request = {"path": str(tmp_path), "workspace_id": workspace_id}
            key = {"Idempotency-Key": str(uuid4())}
            pre_auth = len(used_tokens)
            assert machine.post(checkout, json=request, headers=key).status_code == 401
            assert (
                machine.post(
                    checkout,
                    json={**request, "url": "https://elsewhere.invalid"},
                    headers={**key, **_bearer(world.secret)},
                ).status_code
                == 422
            )
            assert len(used_tokens) == pre_auth
            denied = machine.post(checkout, json=request, headers={**key, **_bearer(user)})
            assert denied.status_code in (403, 404), denied.text
            assert used_tokens[-1] == user
            allowed = machine.post(checkout, json=request, headers={**key, **_bearer(world.secret)})
            assert allowed.status_code == 200, allowed.text
            assert allowed.json() == {"workspace_id": workspace_id, "request_id": key["Idempotency-Key"]}
            drop_after_admission = True
            interrupted = machine.post(checkout, json=request, headers={**key, **_bearer(world.secret)})
            assert interrupted.status_code == 503, interrupted.text

            down = True
            assert machine.get(f"{_PREFIX}/local/status").status_code == 200
            status = machine.get(f"{_PREFIX}/instance/status", headers=_bearer(world.secret))
            assert status.json()["connection"] == "unavailable"
            assert machine.get(setting, headers=owner_session).json()["value"] == "dark"
            assert machine.get(setting, headers=_bearer(world.secret)).status_code == 401
            assert (
                machine.post(checkout, json=request, headers={**key, **_bearer(world.secret)}).status_code
                == 503
            )
            setting_reply = machine.put(
                f"{_PREFIX}/settings/context.selection",
                json={"value": {"workspace_id": str(uuid4())}},
                headers={**owner_session, **_bearer(world.secret)},
            )
            assert setting_reply.status_code == 503
            assert machine.delete(f"{_PREFIX}/session", headers={_SESSION: person_handle}).status_code == 204
            assert machine.get(setting, headers={_SESSION: person_handle}).status_code == 401
            store.profiles["second"] = replace(store.profiles["second"], revision=uuid4())
            assert machine.get(setting, headers={_SESSION: other_handle}).status_code == 401
            clock.advance(timedelta(minutes=11))
            assert machine.get(setting, headers=owner_session).status_code == 401

        with TestClient(api, base_url=_MACHINE_URL, client=("127.0.0.1", 8080)) as network:
            assert network.get(f"{_PREFIX}/local/status").status_code == 403
    world.core.close()


def test_machine_socket_permissions_and_exclusive_binding(tmp_path: Path) -> None:
    path = tmp_path / "private" / "api.sock"
    with _listen(path):
        assert path.parent.stat().st_mode & 0o777 == 0o700
        assert path.stat().st_mode & 0o777 == 0o600

        def second_listener() -> None:
            with _listen(path):
                pytest.fail("A second listener acquired the machine socket")

        with ThreadPoolExecutor(max_workers=1) as executor:
            with pytest.raises(SkmError) as caught:
                executor.submit(second_listener).result(timeout=2)
            assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert not path.exists()
    path.symlink_to(tmp_path / "unrelated")
    with pytest.raises(SkmError) as caught, _listen(path):
        pytest.fail("A symlink acquired the machine socket")
    assert caught.value.code is ErrorCode.SECRET_PERMISSIONS
    assert path.is_symlink()


def test_expected_instance_precedes_dispatch_and_http_client_checks_every_response(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    try:
        with TestClient(_project_api(world), base_url=BASE) as http:
            right = world.core.instance_id
            wrong = uuid4()
            blocked = http.post(
                "/api/v1/workspaces",
                json={"slug": "wrong-instance", "title": "Wrong"},
                headers={**world.headers, "SKM-Instance-Id": str(wrong)},
            )
            assert blocked.status_code == 422, blocked.text
            assert blocked.headers["SKM-Instance-Id"] == str(right)
            assert "wrong-instance" not in http.get("/api/v1/workspaces", headers=world.headers).text
            client = _http(tmp_path, http, world.secret, right)
            assert isinstance(client.ask(access.WhoAmI()), access.WhoAmIView)

            def wrong_instance(response: httpx.Response) -> None:
                assert response.request.headers["SKM-Instance-Id"] == str(right)
                response.headers["SKM-Instance-Id"] = str(wrong)

            http.event_hooks["response"] = [wrong_instance]
            with pytest.raises(SkmError) as caught:
                client.ask(access.WhoAmI())
            assert caught.value.code is ErrorCode.CONFIG_INVALID
    finally:
        world.core.close()


def test_lost_project_write_response_reuses_receipt_and_closes_after_purge(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    try:
        with TestClient(_project_api(world), base_url=BASE) as http:
            pinned = world.core.instance_id
            client = _http(tmp_path, http, world.secret, pinned)
            client.ask(access.WhoAmI())
            safe_until = client.safe_retry_deadline()
            assert safe_until - world.core.clock.now() == world.core.bus.idempotency_retention
            command = workspace.CreateWorkspace(slug="once", title="Once")
            key = uuid4().hex
            sent: list[tuple[str, bytes]] = []

            def lost_after_commit(response: httpx.Response) -> None:
                assert response.status_code == 201, response.text
                assert response.request.headers["SKM-Instance-Id"] == str(pinned)
                assert response.request.headers["SKM-Idempotency-Deadline"] == safe_until.isoformat()
                sent.append((response.request.headers["Idempotency-Key"], response.request.content))
                if len(sent) == 1:
                    raise httpx.ReadError("synthetic lost response")

            http.event_hooks["response"] = [lost_after_commit]
            with pytest.raises(SkmError) as caught:
                client.dispatch_before(command, idempotency_key=key, safe_until=safe_until)
            assert caught.value.code is ErrorCode.BACKEND_UNAVAILABLE

            restarted = _http(tmp_path, http, world.secret, pinned)
            restarted.dispatch_before(command, idempotency_key=key, safe_until=safe_until)
            assert len(sent) == 2
            assert sent[0] == sent[1]
            http.event_hooks["response"] = []
            clock = cast("FrozenClock", world.core.clock)
            clock.advance(world.core.bus.idempotency_retention + timedelta(seconds=1))
            with world.core.uow_factory(world.meta()) as uow:
                assert uow.repo(IdempotencyStore).purge_expired(clock.now(), limit=100) > 0
                uow.commit()
            with pytest.raises(SkmError) as caught:
                restarted.dispatch_before(command, idempotency_key=key, safe_until=safe_until)
            assert caught.value.details["reason"] == "idempotency_window_closed"
            assert http.get("/api/v1/workspaces", headers=world.headers).text.count('"slug":"once"') == 1
    finally:
        world.core.close()
