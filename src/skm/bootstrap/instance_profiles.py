"""Verify and activate named project profiles on the local machine."""

from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from skm.bootstrap.instance_secrets import instance_details, open_http_client
from skm.bootstrap.local_postgres import (
    installation_id_from_env,
    local_postgres_state,
    machine_database_refs,
    managed_postgres,
    mark_managed_postgres,
    prepare_machine_storage,
    provision_local_postgres,
)
from skm.bootstrap.machine import (
    https_origin,
    open_machine_store,
    pin_machine_config,
    resolve_machine_profile,
)
from skm.bootstrap.machine_access import require_human_identity
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, SkmError, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import WhoAmI
from skm.platform.config.bootstrap import BOOTSTRAP_URN, BootstrapConfig, configure_bootstrap
from skm.platform.config.secrets import SecretRef
from skm.platform.config.sources.bootstrap import NewProfile, add_profile
from skm.platform.generated.queries import Doctor
from skm.platform.generated.results import DoctorResult
from skm.platform.machine import MachineProfile

__all__ = ["activate_http_profile", "verified_checkout_marker", "verified_config"]


def verified_checkout_marker(start: Path) -> JsonObject | None:
    from skm.adapters.git.repo_inspect import GitRepositoryInspector
    from skm.modules.workspace.domain.checkout_marker import marker_to_document

    inspector = GitRepositoryInspector()
    marker = inspector.read_marker(inspector.toplevel(start))
    return None if marker is None else marker_to_document(marker)


def verified_config(
    config: BootstrapConfig,
    name: str,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
) -> BootstrapConfig:
    installation = config.installation_id
    if installation is None and config.machine_database_url is None:
        if config.access_mode == "http":
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "HTTP profile requires a verified machine pin")
        return config
    store = open_machine_store(config, environ, on_secret=on_secret)
    if installation is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine installation ID is missing")
    return pin_machine_config(config, resolve_machine_profile(store, installation, name))


def _verify_hub(
    config: BootstrapConfig, environ: Mapping[str, str], on_secret: Callable[[str], None]
) -> UUID:
    try:
        with closing(open_http_client(config, environ, on_secret=on_secret)) as client:
            doctor = client.ask(Doctor(only=("platform.instance",)))
            if not isinstance(doctor, DoctorResult):
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Backend returned invalid identity details")
            identity, _ = instance_details(doctor, config.instance_id)
        with closing(
            open_http_client(replace(config, instance_id=identity), environ, on_secret=on_secret)
        ) as client:
            require_human_identity(client.ask(WhoAmI()))
    except OSError:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Could not load the HTTPS trust bundle") from None
    except SkmError as error:
        status = error.details.get("status")
        if type(status) is int and 300 <= status < 400:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "HTTPS profile verification refuses redirects"
            ) from None
        raise
    return identity


def _candidate_config(new: NewProfile, home: Path, expected: UUID | None) -> BootstrapConfig:
    new.validate()
    if new.endpoint is None or new.credential is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "HTTP requires an endpoint and credential")
    https_origin(new.endpoint)
    if urlsplit(new.endpoint).path != "/api/v1":
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "HTTPS endpoint must have the path /api/v1")
    api: JsonObject = {"endpoint": new.endpoint, "credential": new.credential}
    if new.ca_bundle is not None:
        api["ca_bundle"] = str(new.ca_bundle)
    doc: JsonObject = {"schema": BOOTSTRAP_URN, "access": {"mode": "http"}, "api": api}
    if expected is not None:
        doc["instance_id"] = str(expected)
    return configure_bootstrap("env", doc, {}, home)


def activate_http_profile(
    target: Path,
    new: NewProfile,
    environ: Mapping[str, str],
    home: Path,
    *,
    on_secret: Callable[[str], None],
    expected: UUID | None,
    previous: BootstrapConfig | None = None,
) -> None:
    candidate = _candidate_config(new, home, expected)
    if previous is not None:
        _verify_hub(previous, environ, on_secret)
    identity = _verify_hub(candidate, environ, on_secret)
    verified = replace(new, instance_id=identity)

    def persist(document: JsonObject) -> None:
        root = local_postgres_state(environ, home)
        data = Path(environ.get("XDG_DATA_HOME") or home / ".local/share").absolute()
        document.setdefault("paths", {"state_dir": str(root), "blobs_root": str(data / "skm/blobs")})
        setup = configure_bootstrap(str(target), document, environ, home, instance=new.name)
        managed = managed_postgres(root)
        if setup.machine_database_url is None or managed is not None:
            managed = provision_local_postgres(
                root,
                managed.mode if managed else "client",
                setup.installation_id,
                environ,
                on_secret=on_secret,
            )
        installation = (
            managed.installation_id
            if managed
            else setup.installation_id or installation_id_from_env(environ) or uuid4()
        )
        document["installation_id"] = str(installation)
        if refs := machine_database_refs(managed, environ):
            document["machine_database"] = refs
        setup = configure_bootstrap(str(target), document, environ, home, instance=new.name)
        prepare_machine_storage(setup, environ, on_secret=on_secret)
        _persist_pin(setup, candidate, identity, previous, environ, on_secret)
        if managed is not None:
            mark_managed_postgres(setup.state_dir, managed)

    add_profile(target, verified, home=home, replace_http=previous is not None, before_write=persist)


def _persist_pin(
    setup: BootstrapConfig,
    candidate: BootstrapConfig,
    identity: UUID,
    previous: BootstrapConfig | None,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
) -> None:
    store = open_machine_store(setup, environ, on_secret=on_secret)
    installation, name = setup.installation_id, setup.instance_profile
    endpoint, credential = candidate.api_endpoint, candidate.api_credential
    if installation is None or name is None or endpoint is None or not isinstance(credential, SecretRef):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "A named machine profile and credential are required"
        )
    profile = MachineProfile(
        installation, name, identity, https_origin(endpoint), endpoint, credential, candidate.api_ca_bundle
    )
    current = store.get_profile(installation, name)
    if previous is not None:
        if current is None or pin_machine_config(previous, current) != previous:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Machine profile changed during rebind")
    elif current is not None and replace(current, revision=None) == profile:
        # A retry after the DB commit can finish writing the bootstrap document.
        return
    elif any(
        row.instance_id == identity and row.origin != profile.origin
        for row in store.list_profiles(installation)
    ):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Instance UUID is pinned to another origin. Use instance rebind"
        )
    if not store.put_profile(profile, expected=current if previous is not None else None):
        raise Conflict(ErrorCode.ALREADY_EXISTS, "Instance is already pinned on this installation")
