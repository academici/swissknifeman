"""HTTP worker main refuses a registration that belongs to a different host."""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from skm.entrypoints.worker.main import main
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.platform.config.bootstrap import BootstrapConfig


def test_http_worker_rejects_a_registration_for_another_host_and_closes_the_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    remote = SimpleNamespace(host_id=uuid4(), close=lambda: closed.append(1))
    client = SimpleNamespace(
        dispatch=lambda *args, **kwargs: None,
        new_idempotency_key=lambda: "idem",
    )
    monkeypatch.setattr(
        "skm.entrypoints.worker.main.build_http_worker",
        lambda *args, **kwargs: (remote, client),
    )
    monkeypatch.setattr(
        "skm.entrypoints.worker.main.run_composed_worker",
        lambda *args, **kwargs: pytest.fail("must not start the worker loop"),
    )
    bootstrap = cast(BootstrapConfig, SimpleNamespace(access_mode="http"))
    request = cast(JsonObject, {"host_id": str(uuid4()), "worker_id": str(uuid4())})
    with pytest.raises(ValidationFailed, match="different host") as caught:
        main(request=request, bootstrap=bootstrap, environ={})
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert closed == [1]
