from pathlib import Path
from typing import override

import pytest

from skm.adapters.git.excludes import GitInfoExcludes
from skm.adapters.git.runner import validate_repository_trust
from skm.adapters.research.codegraph import NativeCodeGraphAdapter
from skm.adapters.research.retry import ResearchSources, SourceBusy, SourceFailed
from skm.kernel.cancel import CancelSource, CancelToken
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.research import ResearchQuerySpec, ResearchTier, SourceQuery
from skm.modules.context.domain.research_rules import plan_sources

_QUERY = ResearchQuerySpec("Symbol", (), "standard", 1, True, False)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    info = root / ".git/info"
    info.mkdir(parents=True)
    (info / "exclude").write_bytes(b"# existing rule\n/existing\n")
    return root


def test_native_source_plan_is_checkout_bound_and_in_codegraph_tier() -> None:
    settings: JsonObject = {
        "sources": {
            "web": {"kind": "command", "tier": "external_search", "order": 1},
            "graph": {"kind": "codegraph", "tier": "codegraph", "reads_checkout": False},
            "docs": {"kind": "filesystem", "tier": "local_docs", "order": 100},
        }
    }
    sources = plan_sources(settings, _QUERY)
    assert [source.tier for source in sources] == [
        ResearchTier.LOCAL_DOCS,
        ResearchTier.CODEGRAPH,
        ResearchTier.EXTERNAL_SEARCH,
    ]
    graph = sources[1]
    assert graph.reads_checkout
    adapter = NativeCodeGraphAdapter(validate_repository_trust, GitInfoExcludes())
    assert not adapter.validate_config(graph)
    registry = ResearchSources({"codegraph": adapter})
    assert registry.get("codegraph").kind == "codegraph"
    assert registry.checkout_state({"main": "/checkout"}, CancelSource().token, source=graph) is None


def test_native_source_refuses_host_overrides_and_other_tiers() -> None:
    settings: JsonObject = {
        "sources": {
            "graph": {
                "kind": "codegraph",
                "tier": "external_search",
                "argv": ["/unexpected"],
                "roots": ["/outside"],
                "env_allow": ["UNEXPECTED"],
                "timeout_seconds": 9999,
            }
        }
    }
    (source,) = plan_sources(settings, _QUERY)
    adapter = NativeCodeGraphAdapter(validate_repository_trust, GitInfoExcludes())
    assert set(adapter.validate_config(source)) == {"tier", "argv_env_or_roots", "timeout_seconds"}
    with pytest.raises(SourceFailed) as caught:
        adapter.search(source, SourceQuery("Symbol", 1, "standard", {}), cancel=CancelSource().token)
    assert caught.value.code == ErrorCode.RESEARCH_SOURCE_INVALID


def test_missing_cli_reports_doctor_and_leaves_excludes_untouched(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exclude = checkout / ".git/info/exclude"
    old = exclude.read_bytes()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    adapter = NativeCodeGraphAdapter(validate_repository_trust, GitInfoExcludes())
    cancel = CancelSource().token
    doctor = adapter.manage("doctor", str(checkout), cancel=cancel)
    assert doctor["healthy"] is False
    assert doctor["installed"] is False
    with pytest.raises(CapabilityUnavailable) as caught:
        adapter.manage("init", str(checkout), cancel=cancel)
    assert caught.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert exclude.read_bytes() == old


@pytest.mark.parametrize("entry", [".codegraph", ".codegraph/codegraph.db", ".codegraph/codegraph.db-wal"])
def test_rejects_linked_index_paths(checkout: Path, tmp_path: Path, entry: str) -> None:
    external = tmp_path / "external"
    external.mkdir()
    link = checkout / entry
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(external, target_is_directory=True)
    adapter = NativeCodeGraphAdapter(validate_repository_trust, GitInfoExcludes())
    with pytest.raises(ValidationFailed) as error:
        adapter.manage("init", str(checkout), cancel=CancelSource().token)
    assert error.value.code == ErrorCode.REPOSITORY_UNSAFE
    assert not list(external.iterdir())
    assert b"/.codegraph/" not in (checkout / ".git/info/exclude").read_bytes()


class _FailingCodeGraph(NativeCodeGraphAdapter):
    @staticmethod
    @override
    def _run(
        executable: str, args: tuple[str, ...], env: dict[str, str], cancel: CancelToken, timeout: float
    ) -> bytes:
        del executable, env, cancel, timeout
        if args[0] == "query":
            raise SourceBusy("timeout")
        return b'{"initialized": true, "projectPath": "/other/checkout"}'


def test_status_cannot_report_parent_index_and_query_timeout_remains_retryable(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = str(checkout)
    monkeypatch.setattr("skm.adapters.research.codegraph.shutil.which", lambda *_, **__: "/bin/codegraph")
    adapter = _FailingCodeGraph(validate_repository_trust, GitInfoExcludes())
    cancel = CancelSource().token
    with pytest.raises(CapabilityUnavailable, match="CodeGraph command failed"):
        adapter.manage("status", root, cancel=cancel)
    with pytest.raises(PreconditionFailed, match="graph init"):
        adapter.manage("index", root, cancel=cancel)
    (checkout / ".codegraph").mkdir()
    (checkout / ".codegraph/codegraph.db").touch()
    settings: JsonObject = {"sources": {"graph": {"kind": "codegraph", "tier": "codegraph"}}}
    (source,) = plan_sources(settings, _QUERY)
    with pytest.raises(SourceBusy):
        adapter.search(source, SourceQuery("Symbol", 1, "standard", {"main": root}), cancel=cancel)


def test_native_codegraph_search_confines_index_hits(checkout, monkeypatch):
    import json

    (checkout / ".codegraph").mkdir()
    (checkout / ".codegraph/codegraph.db").touch()
    calls = []

    def query(_binary, argv, _env, _cancel, _timeout):
        calls.append(argv)
        return json.dumps(
            [
                {
                    "node": {
                        "filePath": path,
                        "qualifiedName": "Symbol",
                        "kind": "function",
                        "startLine": 3,
                        "endLine": 4,
                        "signature": "()",
                    }
                }
                for path in ("../outside.py", ".env", "target.py")
            ]
        ).encode()

    monkeypatch.setattr(
        "skm.adapters.research.codegraph.shutil.which", lambda *_args, **_kwargs: "/codegraph"
    )
    monkeypatch.setattr(NativeCodeGraphAdapter, "_run", staticmethod(query))
    adapter = NativeCodeGraphAdapter(validate_repository_trust, GitInfoExcludes())
    settings: JsonObject = {"sources": {"graph": {"kind": "codegraph", "tier": "codegraph"}}}
    (config,) = plan_sources(settings, _QUERY)
    result = adapter.search(
        config,
        SourceQuery(_QUERY.text, 1, "standard", {"repo": str(checkout)}),
        cancel=CancelSource().token,
    )
    (doc,) = result.documents
    assert doc.origin == "mcp:codegraph/repo/target.py#L3"
    assert doc.locator == {"line_from": 3, "line_to": 4}
    assert "Symbol()" in (doc.text or "")
    assert calls[0][-2:] == ("--", "Symbol")
