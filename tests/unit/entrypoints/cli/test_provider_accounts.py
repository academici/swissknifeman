import io
import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from skm.adapters.resources.upstream_http import HttpUpstreamFetcher
from skm.bootstrap import provider_accounts
from skm.bootstrap.runtimes import build_provider_pool
from skm.entrypoints.cli.main import main


def test_host_registry_and_probe_from_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "skm/provider-pool.toml"
    config.parent.mkdir()
    config.write_text(
        '[groups]\nopus = "opus"\nfast = ""\nweekly = ""\npaid = ""\nslow = ""\nother = ""\n'
        '[slots.primary]\nruntime_id = "claude_code"\n[slots.primary.quota_urls]\n'
        + "".join(
            f'{key} = "https://quota.test/{key}"\n' for key in ("opus", "fast", "weekly", "paid", "slow")
        ),
        encoding="utf-8",
    )
    env = {"XDG_CONFIG_HOME": str(tmp_path), "HOME": str(tmp_path)}
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    seen = []

    def open_url(request: Request, *, timeout: float):
        path = request.selector.strip("/")
        seen.append(path)
        status = {"paid": 402, "fast": 429, "slow": 529}.get(path)
        if status:
            raise HTTPError(request.full_url, status, "unavailable", Message(), None)
        if path == "weekly":
            return io.BytesIO(b"invalid")
        return io.BytesIO(b'{"remaining":7,"executed_by":"spoof","reported_model":"opus"}')

    fetcher = HttpUpstreamFetcher(urlopen=open_url)
    monkeypatch.setattr(provider_accounts, "HttpUpstreamFetcher", lambda: fetcher)
    out = io.StringIO()
    assert main(["accounts", "--json"], environ=env, stdout=out) == 0
    assert json.loads(out.getvalue())["result"] == [
        {"runtime_id": "claude_code", "slot_id": "primary", "host_dispatches_tools": False}
    ]
    assert not seen
    pool = build_provider_pool(tmp_path / "pool")
    assert pool.acquire("primary", "test", ttl_seconds=60) is not None

    out = io.StringIO()
    assert main(["--json", "providers", "probe", "--registry", str(config)], environ=env, stdout=out) == 0
    assert seen == ["opus", "fast", "weekly", "paid", "slow"]
    readings = json.loads(out.getvalue())["result"]
    assert [(r["group"]["group_id"], r["state"], r["remaining"]) for r in readings] == [
        ("opus", "available", 7),
        ("fast", "rate_limited", None),
        ("weekly", "unknown", None),
        ("paid", "payment_required", None),
        ("slow", "overloaded", None),
        ("other", "unknown", None),
    ]
    assert all(r["reported_model"] is None for r in readings)
    assert readings[0]["opus_fallback"] is None


def test_unconfigured_host_and_missing_explicit_registry(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path), "HOME": str(tmp_path)}
    out = io.StringIO()
    assert main(["providers", "probe"], environ=env, stdout=out) == 0
    assert "no provider accounts registered" in out.getvalue()
    assert main(["accounts", "--registry", str(tmp_path / "missing")], environ=env, stderr=io.StringIO()) != 0
