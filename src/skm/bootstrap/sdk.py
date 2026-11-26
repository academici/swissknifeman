"""Open an authenticated SDK transport from the selected HTTP profile."""

import os
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from skm.application_bus.client import SkmClient
from skm.bootstrap.instance_secrets import open_http_client
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.platform.config.bootstrap import load_bootstrap

__all__ = ["connect"]


@contextmanager
def connect(*, profile: str | None = None, config: Path | None = None) -> Generator[SkmClient]:
    """Load the profile's endpoint, TLS and credentials. Close the transport on exit."""
    settings = load_bootstrap(str(config) if config else None, os.environ, Path.home(), instance=profile)
    if settings.access_mode != "http":
        raise error_for(ErrorCode.CONFIG_INVALID, "SDK connection requires an HTTP profile")
    if settings.installation_id is not None or settings.machine_database_url is not None:
        from skm.bootstrap.instance_profiles import verified_config

        settings = verified_config(
            settings, settings.instance_profile or "default", os.environ, lambda _: None
        )
    with closing(open_http_client(settings, os.environ)) as client:
        yield client
