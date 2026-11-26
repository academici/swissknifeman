"""M4 uses production host operations, the real bus and immutable pack payloads."""

from pathlib import Path
from typing import Any

from contracts.context.harness import _profile_toml, core_pack
from contracts.extensions.harness import pack_payload
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.application_bus.host import HostServices
from skm.bootstrap.modules import MANIFESTS
from skm.kernel.cancel import CancelSource
from skm.kernel.gateways import GatewayTable
from skm.kernel.ports_uow import Surface
from skm.modules.extensions.ports import BuiltinPacks, PackReader
from skm.platform.logging.logger import get_logger

ROOT = Path(__file__).resolve().parents[4]


def core(side: Any, version: str, body: str) -> None:
    files = {f.path: f.content.decode() for f in core_pack(version, system_body=body).files}
    files["workflows/reviewed-development.toml"] = (
        (ROOT / "tests/fixtures/corpus/examples/execution/workflows/quick-fix.toml")
        .read_text()
        .replace('id = "quick-fix"', 'id = "reviewed-development"')
    )
    side.app.gateways.get(BuiltinPacks).current = (pack_payload("core", version, files=files),)


def host(side: Any) -> Any:
    services = HostServices(
        side.host1,
        Surface.CLI,
        GatewayTable({PackReader: FilesystemPackReader()}, "host_gateway"),
        dict,
        {s.name: s for m in MANIFESTS for s in m.host_operations},
    )
    return lambda: services.context(
        client=side.client, cancel=CancelSource().token, log=get_logger("test.m4")
    )


def overlay(root: Path, version: str, *, config: str = "", trust: str = "operator") -> Path:
    files = {
        "prompts/shared/system.md"
        if trust == "operator"
        else "prompts/shared/vendor.md": f"M4 overlay {version}: café \u0435\u0308 🧪\n"
    }
    if trust == "operator":
        files["agent-profiles/executor.toml"] = _profile_toml("executor", version)
    payload = pack_payload(
        "m4-overlay",
        version,
        trust=trust,
        extra_manifest=(
            f"[config]\n{config}\n"
            + (
                '[[overrides]]\nkind = "prompt_block"\nkey = "shared/system"\n'
                'reason = "M4 pinned operator instructions"\n'
                '[[overrides]]\nkind = "agent_profile"\nkey = "executor"\n'
                'reason = "M4 pinned executor profile"\n'
                if trust == "operator"
                else ""
            )
        ),
        files=files,
    )
    root.mkdir(parents=True)
    (root / "pack.toml").write_text(payload.manifest_text)
    for item in payload.files:
        path = root / item.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.content)
    return root
