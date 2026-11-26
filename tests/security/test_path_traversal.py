"""Portable plan inputs and checkout document paths stay inside their roots (S13)."""

from pathlib import Path
from typing import Any, cast

import pytest

from contracts.context.harness import _spec_doc
from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from security.test_blob_access import assert_private_output, denial_checks, files_under
from skm.adapters.checkout_fs.docs import LocalDocsCheckoutFs
from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.adapters.git.host_inputs import GitCheckoutReader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.exports.domain.docs_push import safe_pattern
from skm.modules.planning.public import ImportSpecification
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

UNSAFE_PATHS = ("../outside.md", "/etc/passwd", "docs/\x00.md")
PRIVATE = "outside-file-private-marker-5021"


@pytest.mark.parametrize("path", UNSAFE_PATHS)
def test_vault_export_target_and_checkout_read_refuse_unsafe_paths(
    tmp_path: Path,
    path: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    (tmp_path / "outside.md").write_text(PRIVATE)
    before = files_under(tmp_path)

    with pytest.raises(SkmError) as export:
        LocalVaultFs(root).create_new(path, b"unauthorized export")
    assert export.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET
    with pytest.raises(SkmError) as pattern:
        safe_pattern(path)
    assert pattern.value.code is ErrorCode.SCHEMA_INVALID
    read = GitCheckoutReader({"repo": root}).read("repo", path, max_bytes=100, follow_symlinks=False)
    assert (read.status, read.data, read.size) == ("path_invalid", None, None)
    assert_private_output(
        (export.value, export.value.details, pattern.value, read, capsys.readouterr()), PRIVATE
    )
    assert files_under(tmp_path) == before


@pytest.mark.parametrize("path", UNSAFE_PATHS)
def test_plan_import_refuses_unsafe_repository_reads(
    exec_side: ExecSide,
    tmp_path: Path,
    path: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    side = exec_side
    (tmp_path / "outside.md").write_text(PRIVATE)
    document = _spec_doc(side.fv1)
    (item,) = cast("list[JsonObject]", document["items"])
    item["reads"] = [
        {"kind": "repository_path", "mount": "repo", "path": path, "why": "Read source", "required": True}
    ]
    command = ImportSpecification(side.proj, cast("Any", document), "new_plan")
    with denial_checks(
        side.app,
        tmp_path,
        dsn=side.dsn,
        schemas=("artifacts", "planning", "workspace"),
        capsys=capsys,
        private=(PRIVATE,),
    ) as check:
        with pytest.raises(SkmError) as rejected:
            side.client.dispatch(command, idempotency_key="reject-unsafe-import")
        check((rejected.value, rejected.value.details))
    assert rejected.value.code in {ErrorCode.INVALID_REFERENCE, ErrorCode.SCHEMA_INVALID}


class _NoReadBudget:
    @property
    def remaining(self) -> int:
        pytest.fail("protected document read reached the byte budget")

    def check(self, **_kwargs: object) -> None:
        pytest.fail("protected document read reached the byte budget")


@pytest.mark.parametrize(
    "path", [".env", "docs/.env.local", "docs/service.pem", ".git/config", ".skm/owner.token"]
)
def test_document_export_will_not_read_sensitive_checkout_paths(
    tmp_path: Path,
    path: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "checkout"
    protected = root / path
    protected.parent.mkdir(parents=True)
    protected.write_text(PRIVATE)
    vault = tmp_path / "vault"
    vault.mkdir()
    before = files_under(tmp_path)
    with (
        LocalDocsCheckoutFs(()).open_checkout(str(root), vault_root=str(vault)) as tree,
        pytest.raises(SkmError) as rejected,
    ):
        tree.read(path, 1024, _NoReadBudget())
    assert rejected.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET
    assert_private_output((rejected.value, rejected.value.details, capsys.readouterr()), PRIVATE)
    assert files_under(tmp_path) == before
