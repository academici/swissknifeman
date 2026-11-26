"""Open machine storage and enforce the instance pin at the composition boundary."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from ipaddress import IPv6Address
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from skm.adapters.secrets.env import EnvSecretResolver
from skm.adapters.secrets.file import FileSecretResolver
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.secrets import SecretResolvers
from skm.platform.config.sources.bootstrap import cli_state_path
from skm.platform.machine import MachineProfile, MachineStore

__all__ = [
    "https_origin",
    "machine_socket_path",
    "open_machine_store",
    "pin_machine_config",
    "resolve_machine_profile",
]


def open_machine_store(
    bootstrap: BootstrapConfig,
    environ: Mapping[str, str],
    *,
    on_secret: Callable[[str], None] = lambda _value: None,
) -> MachineStore:
    """Open the unprivileged machine DSN and check the provisioned installation identity."""
    from skm.adapters.postgres.machine import PostgresMachineStore

    ref, installation = bootstrap.machine_database_url, bootstrap.installation_id
    if ref is None or installation is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine storage requires a DSN and installation ID")
    dsn = SecretResolvers((EnvSecretResolver(environ), FileSecretResolver()), on_reveal=on_secret)
    store = PostgresMachineStore(dsn.resolve(ref).reveal())
    if store.get_installation_id() != installation:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Machine database belongs to a different installation"
        )
    return store


def https_origin(endpoint: str) -> str:
    """Return the HTTPS origin accepted for a verified machine profile."""
    try:
        url = urlsplit(endpoint)
        if (
            url.scheme != "https"
            or url.hostname is None
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(
                ord(character) < 33 or character.isspace() or ord(character) == 127 for character in endpoint
            )
            or "\\" in endpoint
        ):
            raise ValueError
        host = url.hostname.encode("idna").decode("ascii")
        if ":" in host:
            if "%" in host:
                raise ValueError
            host = f"[{IPv6Address(host).compressed}]"
        elif any(char not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for char in host):
            raise ValueError
        if url.port == 0:
            raise ValueError
        port = f":{url.port}" if url.port not in (None, 443) else ""
    except (ValueError, UnicodeError):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Machine profile requires a valid HTTPS endpoint"
        ) from None
    else:
        return f"https://{host}{port}"


def resolve_machine_profile(store: MachineStore, installation_id: UUID, name: str) -> MachineProfile:
    profile = store.get_profile(installation_id, name)
    if profile is None:
        raise ValidationFailed(ErrorCode.INSTANCE_UNKNOWN, "No verified machine profile with that name")
    origin = f"embedded:{profile.instance_id}" if profile.endpoint is None else https_origin(profile.endpoint)
    if profile.revision is None or profile.origin != origin:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine profile has an invalid identity pin")
    return profile


def pin_machine_config(config: BootstrapConfig, profile: MachineProfile) -> BootstrapConfig:
    if (
        config.installation_id != profile.installation_id
        or (config.instance_id is not None and config.instance_id != profile.instance_id)
        or (config.access_mode == "embedded") != (profile.endpoint is None)
    ):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Bootstrap conflicts with the verified machine profile"
        )
    return replace(
        config,
        instance_id=profile.instance_id,
        api_endpoint=profile.endpoint,
        api_credential=profile.credential_ref,
        api_ca_bundle=profile.ca_bundle,
    )


def machine_socket_path(environ: Mapping[str, str], home: Path, installation: UUID) -> Path:
    return cli_state_path(environ, home).parent / "machine" / str(installation) / "api.sock"
