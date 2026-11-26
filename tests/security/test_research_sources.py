"""Adversarial research ingress: paths, network metadata, secrets and authority."""

import json
import os
from dataclasses import replace
from uuid import uuid4

import pytest

from integration.research._support import command, config, host, json_script, query, spec
from integration.research.test_filesystem_adapter import git
from skm.adapters.research.command import CommandResearchSource, PolicyReply, validate_urls
from skm.adapters.research.filesystem import FilesystemResearchSource, file_at
from skm.adapters.research.retry import ResearchSources, SourceFailed
from skm.kernel.cancel import CancelSource
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.context.domain.research import DocumentTrust, RawDocument, RawSourceReply
from skm.modules.context.host.research_query import research_query
from skm.platform.config.secrets import SecretRef, SecretValue


@pytest.mark.parametrize("root", ["repo:../outside", "repo:/etc", "repo:link", "missing:."])
def test_research_roots_cannot_escape_mount_or_follow_symlinks(tmp_path, root):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "guide.md").write_text("research private")
    (checkout / "link").symlink_to(outside, target_is_directory=True)
    cfg = config(kind="filesystem", roots=[root])
    with pytest.raises((SourceFailed, OSError)):
        FilesystemResearchSource().search(
            cfg, query(mounts={"repo": str(checkout)}), cancel=CancelSource().token
        )


def test_absolute_dotdot_cannot_bypass_allowlist(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "guide.md").write_text("research private")
    cfg = config(kind="filesystem", roots=[str(allowed) + "/../outside"])
    with pytest.raises(SourceFailed):
        FilesystemResearchSource(fs_roots_allow=(str(allowed),)).search(
            cfg, query(), cancel=CancelSource().token
        )


def test_descriptor_open_refuses_raced_parent_symlink_and_hardlink(tmp_path):
    git(tmp_path, "init", "-q")
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (outside / "guide.md").write_text("research private")
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with (
            pytest.raises(OSError, match=r"Not a directory|symbolic link"),
            file_at(root_fd, "docs/guide.md"),
        ):
            pytest.fail("symlink parent was followed")
    finally:
        os.close(root_fd)
    (tmp_path / "hard.md").hardlink_to(outside / "guide.md")
    result = FilesystemResearchSource().search(
        config(kind="filesystem", roots=["repo:."]),
        query(mounts={"repo": str(tmp_path)}),
        cancel=CancelSource().token,
    )
    assert result.documents == ()


def test_git_ignored_file_is_skipped_even_if_tracked(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "guide.md").write_text("research private")
    git(tmp_path, "add", "guide.md")
    (tmp_path / ".gitignore").write_text("guide.md\n")
    result = FilesystemResearchSource().search(
        config(kind="filesystem", roots=["repo:."]),
        query(mounts={"repo": str(tmp_path)}),
        cancel=CancelSource().token,
    )
    assert result.documents == ()


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://10.1.2.3/",
        "http://172.31.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.internal/",
        "https://user:pass@example.com/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
def test_network_policy_drops_private_or_unsupported_document_origins(origin):
    ctx = host(
        sources={
            "docs": {
                "kind": "command",
                "tier": "external_search",
                "argv": list(
                    command(
                        json_script(
                            {"documents": [{"origin": origin, "title": "forbidden", "text": "private"}]}
                        )
                    ).argv
                ),
            }
        }
    )
    result = research_query(
        ctx,
        spec(),
        workspace_id=WorkspaceId(uuid4()),
        project_id=ProjectId(uuid4()),
        step_ref=None,
        mounts={},
    ).results[0]
    assert not result.documents
    assert result.limitations


def test_dns_private_answer_and_mixed_public_private_answers_are_denied(monkeypatch):
    import skm.adapters.research.command as transport

    class Resolver:
        def __init__(self, *args, **kwargs):
            pass

        def exchange(self, _):
            return b'["8.8.8.8", "127.0.0.1"]'

        def close(self):
            pass

    monkeypatch.setattr(transport, "ProcessSession", Resolver)
    with pytest.raises(SourceFailed):
        validate_urls((RawDocument("https://apparently-public.example/", "DNS", "body", {}),))


def test_allowlist_rejection_precedes_dns_and_never_uses_request_to_expand_policy(monkeypatch):
    import skm.adapters.research.command as transport

    def unexpected(*args, **kwargs):
        pytest.fail("denied origin reached DNS")

    monkeypatch.setattr(transport, "validate_urls", unexpected)

    class Adapter:
        kind = "plugin"

        def validate_config(self, config):
            return ()

        def search(self, config, query, *, cancel):
            return RawSourceReply(
                (RawDocument("https://unlisted.example/", "Outside", "body", {}),), None, (), None, ""
            )

    source = ResearchSources({"plugin": Adapter()}).get("plugin")
    reply = source.search(
        config(kind="plugin", url_allow=["allowed.example"]), query(), cancel=CancelSource().token
    )
    assert not reply.documents
    assert isinstance(reply, PolicyReply)
    assert reply.limitations == ("url_not_allowed:unlisted.example",)


def test_external_query_redaction_precedes_execution_ledger_and_capture():
    observed = []

    class Adapter:
        kind = "plugin"

        def validate_config(self, config):
            return ()

        def search(self, config, query, *, cancel):
            observed.append(query.text)
            return RawSourceReply((RawDocument("mcp:docs", "Evidence", query.text, {}),), None, (), None, "")

    ctx = host(
        sources={"docs": {"kind": "plugin", "tier": "external_search"}}, adapters={"plugin": Adapter()}
    )
    secret = "sk-" + "A" * 32
    batch = research_query(
        ctx,
        spec("research " + secret, save_as_material=True),
        workspace_id=WorkspaceId(uuid4()),
        project_id=ProjectId(uuid4()),
        step_ref=None,
        mounts={},
    )
    assert secret not in observed[0]
    assert secret not in json.dumps(ctx.client.commands[0][0].to_json())
    assert all(secret.encode() not in content for content in ctx.client.uploads)
    assert "query_redacted" in batch.results[0].limitations


@pytest.mark.parametrize("tier", ["local_docs", "external_search"])
def test_command_cannot_raise_trust_with_forged_repository_origin(tier):
    ctx = host()
    ctx.config["context.research.sources"]["docs"]["tier"] = tier
    result = research_query(
        ctx,
        spec(),
        workspace_id=WorkspaceId(uuid4()),
        project_id=ProjectId(uuid4()),
        step_ref=None,
        mounts={},
    ).results[0]
    assert result.documents[0].trust_class is DocumentTrust.EXTERNAL
    assert result.documents[0].origin.startswith("mcp:")


def test_command_environment_is_closed_and_skm_names_or_refs_are_refused(monkeypatch):
    monkeypatch.setenv("SKM_TOKEN", "private-worker-token")
    monkeypatch.setenv("DATABASE_URL", "private-database-url")
    script = (
        "import json,os; print(json.dumps({'documents':["
        "{'origin':'mcp:env','title':'Env','text':json.dumps(dict(os.environ))}]}))"
    )
    reply = CommandResearchSource().search(command(script), query(), cancel=CancelSource().token)
    text = reply.documents[0].text
    assert text is not None
    assert "SKM_TOKEN" not in text
    assert "DATABASE_URL" not in text
    for name in ("SKM_TOKEN", "SKM__DATABASE__URL"):
        cfg = command(script, env_allow=[name])
        assert CommandResearchSource().validate_config(cfg)
    ref = SecretRef.parse("secret://env/SKM_TOKEN")
    adapter = CommandResearchSource(
        env_refs={"PROVIDER_TOKEN": ref}, resolve=lambda value: SecretValue(value, "secret")
    )
    with pytest.raises(SourceFailed):
        adapter.search(command(script, env_allow=["PROVIDER_TOKEN"]), query(), cancel=CancelSource().token)


def test_concurrency_gate_is_shared_for_repeated_registry_gets():
    registry = ResearchSources({"command": CommandResearchSource()})
    cfg = config(concurrency=1)
    gate = registry.gate(cfg)
    assert gate.acquire(blocking=False)
    try:
        assert not registry.gate(replace(cfg, concurrency=2)).acquire(blocking=False)
    finally:
        gate.release()
