"""Exercise the host's admission, bounded selection and vault publication boundary."""

import json
import os
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from skm.adapters.checkout_fs.docs import LocalDocsCheckoutFs
from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.exports.host.locate_vault import Budget
from skm.modules.exports.host.push_vault_docs import DocsCheckoutFs, SourceRefused, push_vault_docs
from skm.modules.exports.ports import VaultFs
from skm.modules.workspace.public import CheckoutLocationView, GetProject, ProjectView, ResolveCheckout
from unit.exports.host.test_push_vault_notes import VaultFixture, vault

__all__ = ["vault"]

_PROJECT = uuid4()
_DATA = "référence\n".encode()


class Tree:
    def __init__(self, paths: dict[str, bytes], locator: Path) -> None:
        self.files = paths
        self.locator = locator
        self.opened: list[str] = []
        self.visited = 0

    def open_checkout(self, locator: str, *, vault_root: str):
        assert locator == str(self.locator)
        assert vault_root
        return nullcontext(self)

    def entries(
        self, visit: Callable[[], None], exclude: Callable[[str], bool]
    ) -> Iterator[tuple[str, str | None]]:
        for path in self.files:
            visit()
            self.visited += 1
            yield path, "sensitive_path" if any(map(exclude, path.split("/"))) else None

    def read(self, path: str, max_bytes: int, budget: Budget) -> bytes:
        self.opened.append(path)
        data = self.files[path]
        if len(data) > max_bytes:
            raise SourceRefused("file_too_large")
        budget.check(size=len(data))
        return data


type Fixture = tuple[HostContext, Tree, LocalVaultFs, Mock]


@pytest.fixture
def docs(vault: VaultFixture) -> Fixture:
    ctx, client, fs = vault
    fs.write_atomic(
        ".projects.json", b'{"projects":[{"skm_project":"sample","vault_path":"Project"}]}', replace=True
    )
    who = Mock(spec=WhoAmIView)
    who.modules = {"exports": True}
    who.principal = Mock(kind="human")
    who.token = None
    who.effective_permissions = ("export.run", "file.read")
    locator = fs.root.parent / "checkout"
    location = CheckoutLocationView(uuid4(), uuid4(), str(locator), "active", False)
    project = ProjectView(_PROJECT, uuid4(), "sample", "Sample", "", "active", 1, ())

    def ask(query: object):
        if isinstance(query, WhoAmI):
            assert query.scope_id == _PROJECT
            return who
        if isinstance(query, ResolveCheckout):
            assert query.host_id == ctx.host_id
            assert query.mount_name == "main"
            return location
        assert isinstance(query, GetProject)
        return project

    client.ask.side_effect = ask
    tree = Tree({"README.md": _DATA}, locator)
    ctx = replace(ctx, gateways=GatewayTable({VaultFs: fs, DocsCheckoutFs: tree}, "host_gateway"))
    return ctx, tree, fs, who


def rows(report: JsonObject, key: str) -> list[JsonObject]:
    return cast("list[JsonObject]", report[key])


@pytest.mark.parametrize(
    ("kind", "token", "grants", "enabled"),
    [
        ("worker", None, ["export.run", "file.read"], True),
        ("human", "assignment", ["export.run", "file.read"], True),
        ("service", None, ["export.run"], True),
        ("human", None, ["file.read"], True),
        ("human", None, ["export.run", "file.read"], False),
    ],
)
def test_admission_precedes_filesystem(
    docs: Fixture,
    kind: str,
    token: str | None,
    grants: list[str],
    enabled: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, _, fs, who = docs
    who.principal.kind, who.token = kind, Mock(kind=token) if token else None
    who.effective_permissions, who.modules = grants, {"exports": enabled}
    gateway = Mock(wraps=ctx.gateways)
    locate = Mock(wraps=fs.at)
    monkeypatch.setattr(fs, "at", locate)
    with pytest.raises(SkmError) as caught:
        push_vault_docs(replace(ctx, gateways=gateway), project_id=_PROJECT, force=True)
    assert caught.value.code == (ErrorCode.FORBIDDEN if enabled else ErrorCode.MODULE_DISABLED)
    gateway.get.assert_called_once_with(VaultFs)
    locate.assert_not_called()


def test_no_force_race_and_explicit_replace(docs: Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, tree, fs, who = docs
    who.principal.kind = "service"
    target = "Project/Docs/README.md"
    create = LocalVaultFs.create_new

    def race(self: LocalVaultFs, rel: str, data: bytes) -> bool:
        if rel == target:
            assert create(self, rel, b"foreign")
            planned = list(fs.state().root.glob("docs/*/*/1.json"))
            assert len(planned) == 1
            record = json.loads(planned[0].read_bytes())
            assert record["outcome"] == "planned"
            assert record["classification"] == "restricted"
            assert record["digest"] == "sha256:" + sha256(data).hexdigest()
        return create(self, rel, data)

    monkeypatch.setattr(LocalVaultFs, "create_new", race)
    extra = fs.root / "unrelated.md"
    extra.write_bytes(b"keep")
    report = push_vault_docs(ctx, project_id=_PROJECT)
    assert rows(report, "conflicts")[0]["destination"] == target
    assert (fs.root / target).read_bytes() == b"foreign"
    result = push_vault_docs(ctx, project_id=_PROJECT, force=True)
    assert rows(result, "copied")[0]["classification_basis"] == "conservative_unknown"
    assert (fs.root / target).read_bytes() == _DATA
    assert rows(push_vault_docs(ctx, project_id=_PROJECT), "identical")
    assert tree.opened == ["README.md"] * 3
    assert extra.read_bytes() == b"keep"


def snapshot(root: Path) -> dict[Path, bytes | None]:
    return {p.relative_to(root): p.read_bytes() if p.is_file() else None for p in root.rglob("*")}


def test_dry_run_admits_fresh_bytes_and_rejects_collisions_and_sensitive_names(docs: Fixture) -> None:
    ctx, tree, fs, _ = docs
    tree.files.update(
        dict.fromkeys(
            (
                "a.md",
                "A.md",
                "café.md",
                "cafe\u0301.md",
                ".git/x",
                ".skm/X",
                ".envLOCAL",
                "KEY.PEM",
                "x.key",
                "x.P12",
                "x.PFX",
                "id_rsa.pub",
                "id_dsa2",
                "id_ed25519",
                "credentials.json",
                "secrets.json",
            ),
            b"secret",
        )
    )
    before = snapshot(fs.root.parent)
    report = push_vault_docs(ctx, project_id=_PROJECT, patterns=["**", "*.md"], force=True, dry_run=True)
    assert [row["source"] for row in rows(report, "copied")] == ["README.md"]
    assert len(rows(report, "refused")) == len(tree.files) - 1
    assert tree.opened == ["README.md"]
    assert before == snapshot(fs.root.parent)
    tree.files["README.md"] = b"changed after preview"
    report = push_vault_docs(ctx, project_id=_PROJECT)
    assert rows(report, "copied")[0]["digest"] == "sha256:" + sha256(tree.files["README.md"]).hexdigest()


@pytest.mark.parametrize(
    ("pattern", "refused"), [(".git/config", True), ("**/.git/*.md", True), ("*.md", False)]
)
def test_sensitive_subtree_is_reported_without_opening_it(
    docs: Fixture, monkeypatch: pytest.MonkeyPatch, pattern: str, refused: bool
) -> None:
    ctx, tree, fs, _ = docs
    (tree.locator / ".git").mkdir(parents=True)
    (tree.locator / ".git/config").write_bytes(b"protected bytes")
    (tree.locator / ".git/private.md").write_bytes(b"protected bytes")
    opened = Mock(wraps=os.open)
    monkeypatch.setattr(os, "open", opened)
    gateway = LocalDocsCheckoutFs(())
    ctx = replace(ctx, gateways=GatewayTable({VaultFs: fs, DocsCheckoutFs: gateway}, "host_gateway"))

    report = push_vault_docs(ctx, project_id=_PROJECT, patterns=[pattern], dry_run=True, force=True)

    assert [(row["source"], row["reason"]) for row in rows(report, "refused")] == (
        [(".git", "sensitive_path")] if refused else []
    )
    assert all(call.args[0] not in {".git", "config", "private.md"} for call in opened.call_args_list)
    assert report["partial"] is False


@pytest.mark.parametrize(("count", "pattern"), [(1001, "**"), (10001, "*.md")])
def test_scan_and_selection_caps(docs: Fixture, count: int, pattern: str) -> None:
    ctx, tree, _, _ = docs
    tree.files = dict.fromkeys(map(str, range(count)), b"")
    report = push_vault_docs(ctx, project_id=_PROJECT, patterns=[pattern], dry_run=True)
    assert report["partial"] is True
    assert report["reason"] == "budget_exceeded"
    assert tree.visited <= 10000
    assert not tree.opened


@pytest.mark.parametrize("pattern", ["../README.md", "/README.md", "docs/../a", "C:/docs", "a\\b"])
def test_invalid_glob(docs: Fixture, pattern: str) -> None:
    ctx, tree, _, _ = docs
    with pytest.raises(SkmError):
        push_vault_docs(ctx, project_id=_PROJECT, patterns=[pattern])
    assert not tree.opened


def test_no_patterns_and_ambiguous_mapping(docs: Fixture) -> None:
    ctx, tree, fs, _ = docs
    assert not rows(push_vault_docs(ctx, project_id=_PROJECT, patterns=[], dry_run=True), "copied")
    fs.write_atomic(
        ".projects.json",
        b'{"projects":[{"skm_project":"sample","vault_path":"X"},{"skm_project":"sample","vault_path":"Y"}]}',
        replace=True,
    )
    with pytest.raises(SkmError) as caught:
        push_vault_docs(ctx, project_id=_PROJECT)
    assert caught.value.code == ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN
    assert not tree.opened
    assert not (fs.state().root / "docs").exists()


@pytest.mark.parametrize("as_json", [True, False])
def test_registered_cli_preview(docs: Fixture, as_json: bool) -> None:
    from io import StringIO

    from skm.entrypoints.cli.main import Backend, main

    ctx, tree, fs, _ = docs
    tree.files["docs/design.md"] = b"design"
    output, error = StringIO(), StringIO()
    args = [
        "export",
        "docs-push",
        "--project",
        str(_PROJECT),
        "--mount",
        "main",
        "--pattern",
        "docs/**/*.md",
        "--dry-run",
        "--force",
    ]
    if as_json:
        args.append("--json")
    before = snapshot(fs.root.parent)
    status = main(
        args, backend=lambda *_: Backend(ctx.client, host_factory=lambda: ctx), stdout=output, stderr=error
    )
    assert status == 0, error.getvalue()
    assert "docs/design.md" in output.getvalue()
    assert tree.opened == ["docs/design.md"]
    assert snapshot(fs.root.parent) == before


def test_source_drift_is_refused_without_creating_destination(
    docs: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, tree, fs, _ = docs
    tree.locator.mkdir()
    source = tree.locator / "README.md"
    source.write_bytes(_DATA)
    original = source.stat()
    read = os.read

    def changed(fd: int, size: int) -> bytes:
        data = read(fd, size)
        if os.path.samestat(os.fstat(fd), original):
            source.write_bytes(b"updated README")
        return data

    monkeypatch.setattr(os, "read", changed)
    gateway = LocalDocsCheckoutFs(())
    ctx = replace(ctx, gateways=GatewayTable({VaultFs: fs, DocsCheckoutFs: gateway}, "host_gateway"))
    report = push_vault_docs(ctx, project_id=_PROJECT, force=True)
    assert rows(report, "refused")[0]["reason"] == "source_changed"
    assert not (fs.root / "Project").exists()


@pytest.mark.parametrize("replace_parent", [False, True])
def test_checkout_reader_refuses_symlink_swapped_after_scan(docs: Fixture, replace_parent: bool) -> None:
    ctx, tree, fs, _ = docs
    folder = tree.locator / "docs"
    folder.mkdir(parents=True)
    source = folder / "readme.md"
    source.write_bytes(_DATA)
    foreign = fs.root.parent / "foreign"
    foreign.mkdir()
    (foreign / source.name).write_bytes(b"outside the checkout")

    gateway = LocalDocsCheckoutFs(())
    with gateway.open_checkout(str(tree.locator), vault_root=str(fs.root)) as local:
        assert list(local.entries(lambda: None, lambda _: False)) == [("docs/readme.md", None)]
        if replace_parent:
            folder.rename(tree.locator / "old-docs")
            folder.symlink_to(foreign, target_is_directory=True)
        else:
            source.unlink()
            source.symlink_to(foreign / source.name)
        budget = Budget(ctx, fs)
        remaining = budget.remaining
        with pytest.raises(SkmError) as caught:
            local.read("docs/readme.md", 1024, budget)
        assert caught.value.code == ErrorCode.INTEGRATION_UNSAFE_TARGET
        assert budget.remaining == remaining


def test_checkout_reader_enforces_remaining_budget(docs: Fixture) -> None:
    ctx, tree, fs, _ = docs
    tree.locator.mkdir()
    (tree.locator / "README.md").write_bytes(_DATA)
    gateway = LocalDocsCheckoutFs(())
    with gateway.open_checkout(str(tree.locator), vault_root=str(fs.root)) as local:
        budget = Budget(ctx, fs)
        budget.remaining = len(_DATA) - 1
        with pytest.raises(SkmError) as caught:
            local.read("README.md", 1024, budget)
        assert caught.value.details["reason"] == "budget_exceeded"
        budget.remaining = len(_DATA)
        assert local.read("README.md", 1024, budget) == _DATA
        assert budget.remaining == 0


def test_deadline_during_scan(docs: Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, tree, fs, _ = docs
    tree.files = dict.fromkeys(["a.md", "b.md", "c.md"], b"")
    monkeypatch.setattr(LocalVaultFs, "monotonic", lambda _fs: 60.0 if tree.visited else 0.0)
    before = snapshot(fs.root.parent)
    report = push_vault_docs(ctx, project_id=_PROJECT, dry_run=True)
    assert report["reason"] == "budget_exceeded"
    assert report["partial"] is True
    assert tree.visited == 1
    assert not tree.opened
    assert snapshot(fs.root.parent) == before


@pytest.mark.parametrize("expires_during", ["publish", "outcome"])
def test_deadline_subtracts_admission_time_and_preserves_final_publication(
    docs: Fixture, monkeypatch: pytest.MonkeyPatch, expires_during: str
) -> None:
    ctx, _, fs, _ = docs
    now = 0.0
    monkeypatch.setattr(LocalVaultFs, "monotonic", lambda _fs: now)
    client = cast("Mock", ctx.client)
    ask = client.ask.side_effect
    lock = LocalVaultFs.lock
    create = LocalVaultFs.create_new
    write = LocalVaultFs.write_atomic
    target = "Project/Docs/README.md"

    def slow_admission(query: object):
        nonlocal now
        if now == 0.0:
            assert isinstance(query, WhoAmI)
            now = 55.0
        return ask(query)

    def lock_for_remaining_time(self: LocalVaultFs, vault_id: UUID, *, deadline_seconds: float):
        assert deadline_seconds == 5.0
        return lock(self, vault_id, deadline_seconds=deadline_seconds)

    def publish_at_deadline(self: LocalVaultFs, rel: str, data: bytes) -> bool:
        nonlocal now
        created = create(self, rel, data)
        if expires_during == "publish" and rel == target:
            now = 60.0
        return created

    def write_at_deadline(self: LocalVaultFs, rel: str, data: bytes, *, replace: Literal[True]) -> None:
        nonlocal now
        write(self, rel, data, replace=replace)
        if expires_during == "outcome" and rel.endswith("/outcome.json"):
            now = 60.0

    client.ask.side_effect = slow_admission
    monkeypatch.setattr(LocalVaultFs, "lock", lock_for_remaining_time)
    monkeypatch.setattr(LocalVaultFs, "create_new", publish_at_deadline)
    monkeypatch.setattr(LocalVaultFs, "write_atomic", write_at_deadline)

    report = push_vault_docs(ctx, project_id=_PROJECT)

    digest = "sha256:" + sha256(_DATA).hexdigest()
    assert report["partial"] is True
    assert report["reason"] == "budget_exceeded"
    (copied,) = rows(report, "copied")
    assert copied["digest"] == digest
    assert copied["bytes"] == len(_DATA)
    assert (fs.root / target).read_bytes() == _DATA
    journal = fs.state().root / cast("str", report["host_report"])
    record = json.loads((journal / "1.json").read_bytes())
    assert record["outcome"] == "copied"
    assert record["digest"] == digest
    assert record["bytes"] == len(_DATA)
    assert json.loads((journal / "outcome.json").read_bytes())["reason"] == "budget_exceeded"


def test_write_budget_preserves_already_published_digests(
    docs: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skm.modules.exports.host import push_vault_docs as docs_host

    ctx, tree, fs, _ = docs
    tree.files = {"a.md": b"a" * 4096, "b.md": b"b" * 4096}
    monkeypatch.setattr(docs_host, "_MAX_BYTES", 8192)
    report = push_vault_docs(ctx, project_id=_PROJECT, patterns=["*.md"])
    assert report["reason"] == "budget_exceeded"
    assert report["partial"] is True
    assert rows(report, "copied")[0]["digest"] == "sha256:" + sha256(tree.files["a.md"]).hexdigest()
    assert (fs.root / "Project/Docs/a.md").read_bytes() == tree.files["a.md"]
    assert not (fs.root / "Project/Docs/b.md").exists()
