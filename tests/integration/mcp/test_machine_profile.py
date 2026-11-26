"""Managed MCP transport resolves machine pins before opening HTTP."""

from dataclasses import replace
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest

from skm.bootstrap import instance_profiles
from skm.entrypoints.cli.commands import mcp
from skm.entrypoints.cli.main import main
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Unauthenticated
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.machine import MachineProfile


def test_managed_mcp_resolves_pinned_endpoint_before_sending_stored_bearer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap = tmp_path / "bootstrap.toml"
    installation, hub = uuid4(), uuid4()
    bootstrap.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'installation_id = "{installation}"\n'
        f'instance_id = "{hub}"\n'
        '[access]\nmode = "http"\n'
        '[api]\nendpoint = "https://other.invalid/api/v1"\n'
        'credential = "secret://env/UNPINNED_CREDENTIAL"\n',
        encoding="utf-8",
    )
    ca = tmp_path / "hub.ca"
    pin = MachineProfile(
        installation,
        "default",
        hub,
        "https://verified.invalid",
        "https://verified.invalid/api/v1",
        SecretRef.parse("secret://env/PINNED_CREDENTIAL"),
        ca,
        uuid4(),
    )

    class LocalPins:
        def get_profile(self, installation_id, name):
            assert (installation_id, name) == (installation, "default")
            return pin

    monkeypatch.setattr(instance_profiles, "open_machine_store", lambda *args, **kwargs: LocalPins())
    opened = []

    def safe_transport(config: BootstrapConfig, _environ, *, credential: SecretValue):
        opened.append((config.api_endpoint, config.instance_id, config.api_ca_bundle, credential.reveal()))
        raise Unauthenticated(ErrorCode.UNAUTHENTICATED, "Synthetic peer rejected request")

    monkeypatch.setattr(mcp, "open_http_client", safe_transport)
    environment = {"UNPINNED_CREDENTIAL": "other-fake-token", "PINNED_CREDENTIAL": "pinned-fake-token"}

    def invoke():
        return main(
            ["--bootstrap", str(bootstrap), "mcp", "tools"],
            environ=environment,
            stdout=StringIO(),
            stderr=StringIO(),
        )

    assert invoke() != 0
    assert opened == [(pin.endpoint, hub, ca, "pinned-fake-token")]
    pin = replace(pin, instance_id=uuid4())
    assert invoke() != 0
    assert len(opened) == 1
