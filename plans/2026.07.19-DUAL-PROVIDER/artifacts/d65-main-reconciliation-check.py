#!/usr/bin/env python3
"""Generate and verify the sealed D65-A/D68 main reconciliation manifest."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[3]
MANIFEST_PATH = SCRIPT_PATH.with_name("d65-main-reconciliation.json")
MAIN_ROOT = Path("/home/vostrikov/projects/packages/swissknifeman")
BASE_REF = "90b9e41a4f95083b46e72fe815118f7343db1fe0"
MAIN_REF = "90b9e41a4f95083b46e72fe815118f7343db1fe0"
DELIVERY_REF = "c8c78bd6c8731f1261d5d103ca557f7c4d062bac"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")

PATH_SPECS = {
    "packages/skiller/docs/guide/budget.md": {
        "classification": "matches-base",
        "derived": True,
        "sha256": {
            "base": "8e334989ead4bc2412b357cf0d5ff8a0cb06744e1c827ceb50065a5de1b0771a",
            "main": "8e334989ead4bc2412b357cf0d5ff8a0cb06744e1c827ceb50065a5de1b0771a",
            "delivery": "06d482dfc9da329371be445fd735510ea379f67654254382f6eb3fd00ac088fd",
        },
    },
    "packages/skiller/skills.json": {
        "classification": "matches-base",
        "derived": True,
        "sha256": {
            "base": "e003dfa157fc4f26cab580e655d728b41385f1c43b2037c1ad9ec246cd5faa13",
            "main": "e003dfa157fc4f26cab580e655d728b41385f1c43b2037c1ad9ec246cd5faa13",
            "delivery": "5510a278e8858194e60227bdff908a6b79c703ff1991b9dd88c60a442e012d84",
        },
    },
    "packages/skiller/skills/general/plan-protocol/SKILL.md": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "f854c8f93cb411addb36f47f86cead9a2ccbc87ad73c2e2c7177ad6e43761d3e",
            "main": "9040c533879e56a97c631cfebeb524543de3b9aec379ac2f60ec4a01d1aaa94e",
            "delivery": "774c08776a103c792297ad014fb8cc5c92d943114993912b5afa224b8ade81a9",
        },
    },
    "packages/skiller/skills/general/plan-protocol/SKILL.ru.md": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "29f9c583cd6fc7bdc81dd1443e6fcaca548711757bd5af1d94f17d89e1837e92",
            "main": "ed305ad41de0e2b37bd5d363da8c7f01f436e8d2d649be52e2bca6003f4e9c47",
            "delivery": "096b7acc8f65c9939378cf5136fb62f6d39423fb586dd32fa4160e30e3168500",
        },
    },
    "packages/skiller/skills/general/plan-protocol/snippets/journal-template.md": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "b630cd5d68ca561da82fcd4c8f934c4a507a2fb3bff6ac0fd0bf0e2038fe12ce",
            "main": "5decccbc7f077206a04238f129c61f145d9c8d754c9395e1372dce7c0efd7f06",
            "delivery": "e303cf09d21e1a1f6f5142a0007e2e4e56895c02ef7949d376d5a284d650d0af",
        },
    },
    "packages/task/.claude-plugin/plugin.json": {
        "classification": "matches-delivery",
        "derived": False,
        "sha256": {
            "base": "5e15dd7dc3f766342bbffd3acbe5d5e629ecad7bb05794083909e49dee8cf7fc",
            "main": "7369bfdb65eb322a980f165104d20482d195e5ae07c63d861391968db64df623",
            "delivery": "7369bfdb65eb322a980f165104d20482d195e5ae07c63d861391968db64df623",
        },
    },
    "packages/task/commands/plan-design.md": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "30061392a856a57013f1b32abadb186f8b606b4ca7ffb1fda7f86b3f71fc91b4",
            "main": "4c9637beb99641aea8658b0777f23c5f5df636479e008a62ef9c711dcced71b8",
            "delivery": "883a3423951d23c970be4864f4985c191a8e6b5ecb462c9523cb23bd84e21763",
        },
    },
    "packages/task/lib/task/journal.py": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "77841c46bef3f4c1de81b975504bcaf0f72d7744217274ecf992c8783ecb9c4b",
            "main": "b418eb421f50daf7ec8dfb667e79cc9c37f7fe13f65ee0a44a7575220544b2b7",
            "delivery": "032d0e5cca869c94399306198db1e6ddc153520bb1b8fa62012f56375649d0cd",
        },
    },
    "packages/task/lib/task/plan_lint.py": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "8ea954e4af18eed20779a0d0d60b8f39a5d704db6782f1187d471fecb360ec26",
            "main": "9bc83fd6c61abd83a32846272bb90396996f72768e2342a266cf7d04ee4a4573",
            "delivery": "df6ecbea4bf8c1ada83dd26dd810af323c502718dae4feec11f6deeb8aafcc44",
        },
    },
    "packages/task/tests/test_journal.py": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "bf7bc71b0364c70f9f6ddf954f547ae51eb3f7b7a8115c272555d401ec7127fd",
            "main": "cb840ca4898d97fbf4f8a795b6ec99b2e390a2d6fab56e30676bab893ed0cd25",
            "delivery": "f1c670974d2da565fe9e6d90e01a771f6d85014563274b7b2565803976b7c103",
        },
    },
    "packages/task/tests/test_plan_lint.py": {
        "classification": "conflict",
        "derived": False,
        "sha256": {
            "base": "03db8b71caf79368600e04a67911df61ffb33f401e316377b95543b18641f63e",
            "main": "f35a7d15a91e7a85d821faaf4fb852d48224c7752ac47ffb0e20c545f0987bcd",
            "delivery": "2e4d32043ef36d92ffc2b45a46e64198ceb6a8b58858c793ead316388d936f2d",
        },
    },
}

EXPECTED_COUNTS = {"conflict": 8, "matches-delivery": 1, "matches-base": 2}
EXPECTED_PATHS = tuple(sorted(PATH_SPECS))


class ReconciliationError(RuntimeError):
    """The sealed snapshot or manifest does not match its contract."""


def _run_git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=environment,
    )
    if process.returncode:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise ReconciliationError(f"git {' '.join(args)} failed: {detail}")
    if binary:
        return process.stdout
    return process.stdout.decode("utf-8").strip()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _relative_components(relative_path: str) -> tuple[str, ...]:
    candidate = Path(relative_path)
    if candidate.is_absolute() or not relative_path or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise ReconciliationError(f"path is not a safe relative path: {relative_path}")
    return candidate.parts


def _open_directory_no_symlinks(root: Path) -> int:
    absolute = Path(os.path.abspath(root))
    if not absolute.is_absolute():
        raise ReconciliationError(f"root is not absolute: {root}")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None:
        raise ReconciliationError("Linux O_NOFOLLOW/O_DIRECTORY are required")
    flags = os.O_RDONLY | os.O_CLOEXEC | nofollow | directory
    descriptor = os.open("/", flags)
    try:
        for component in absolute.parts[1:]:
            try:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ReconciliationError(f"unsafe root component: {component}") from exc
                raise
            os.close(descriptor)
            descriptor = next_descriptor
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ReconciliationError(f"root is not a directory: {root}")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _sha256_file(root: Path, relative_path: str) -> str:
    components = _relative_components(relative_path)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None:
        raise ReconciliationError("Linux O_NOFOLLOW/O_DIRECTORY are required")
    root_descriptor = _open_directory_no_symlinks(root)
    descriptor = root_descriptor
    try:
        for component in components[:-1]:
            try:
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_CLOEXEC | nofollow | directory,
                    dir_fd=descriptor,
                )
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ReconciliationError(
                        f"unsafe path component: {relative_path}"
                    ) from exc
                raise
            os.close(descriptor)
            descriptor = next_descriptor
        try:
            file_descriptor = os.open(
                components[-1],
                os.O_RDONLY | os.O_CLOEXEC | nofollow,
                dir_fd=descriptor,
            )
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ReconciliationError(f"symlinked final file: {relative_path}") from exc
            raise
        try:
            if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
                raise ReconciliationError(f"final path is not a regular file: {relative_path}")
            digest = hashlib.sha256()
            with os.fdopen(file_descriptor, "rb", closefd=True) as source:
                file_descriptor = -1
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        finally:
            if file_descriptor >= 0:
                os.close(file_descriptor)
    finally:
        os.close(descriptor)


def _assert_root(root: Path, expected: Path | None = None) -> Path:
    absolute = Path(os.path.abspath(root))
    descriptor = _open_directory_no_symlinks(absolute)
    os.close(descriptor)
    top_level = Path(os.path.abspath(str(_run_git(absolute, "rev-parse", "--show-toplevel"))))
    if top_level != absolute:
        raise ReconciliationError(f"not an exact git root: {absolute}")
    if expected is not None and absolute != Path(os.path.abspath(expected)):
        raise ReconciliationError(f"unexpected git root: {absolute}")
    return absolute


def _resolve_commit(root: Path, commit: str) -> str:
    if not COMMIT_RE.fullmatch(commit):
        raise ReconciliationError(f"mutable or malformed ref is forbidden: {commit}")
    resolved = str(_run_git(root, "rev-parse", f"{commit}^{{commit}}"))
    if resolved != commit:
        raise ReconciliationError(f"ref does not resolve byte-for-byte: {commit}")
    return resolved


def _classification(hashes: dict[str, str]) -> str:
    base = hashes["base"]
    main = hashes["main"]
    delivery = hashes["delivery"]
    if len({base, main, delivery}) == 3:
        return "conflict"
    if main == delivery and main != base:
        return "matches-delivery"
    if main == base and delivery != base:
        return "matches-base"
    raise ReconciliationError("hash triple has no allowed classification")


def _main_is_clean(main_root: Path, relative_path: str) -> bool:
    status = _run_git(main_root, "status", "--porcelain=v1", "--", relative_path, binary=True)
    assert isinstance(status, bytes)
    return status == b""


def build_manifest(
    *,
    main_root: Path = MAIN_ROOT,
    expected_main_ref: str = MAIN_REF,
    require_canonical_main: bool = True,
) -> dict[str, Any]:
    repo_root = _assert_root(REPO_ROOT, REPO_ROOT)
    canonical_main = MAIN_ROOT if require_canonical_main else None
    main_root = _assert_root(main_root, canonical_main)
    refs = {
        "base": _resolve_commit(repo_root, BASE_REF),
        "main": _resolve_commit(main_root, expected_main_ref),
        "delivery": _resolve_commit(repo_root, DELIVERY_REF),
    }
    if str(_run_git(main_root, "rev-parse", "HEAD^{commit}")) != refs["main"]:
        raise ReconciliationError("main HEAD does not match the sealed full ref")

    rows: list[dict[str, Any]] = []
    counts = {key: 0 for key in EXPECTED_COUNTS}
    for relative_path in EXPECTED_PATHS:
        spec = PATH_SPECS[relative_path]
        hashes = {
            "base": _sha256_bytes(
                _run_git(repo_root, "show", f"{refs['base']}:{relative_path}", binary=True)
            ),
            "main": _sha256_file(main_root, relative_path),
            "delivery": _sha256_bytes(
                _run_git(repo_root, "show", f"{refs['delivery']}:{relative_path}", binary=True)
            ),
        }
        if hashes != spec["sha256"]:
            raise ReconciliationError(f"sealed hash triple drifted: {relative_path}")
        classification = _classification(hashes)
        if classification != spec["classification"]:
            raise ReconciliationError(f"classification drifted: {relative_path}")
        main_clean = _main_is_clean(main_root, relative_path)
        derived = bool(spec["derived"])
        if derived and (not main_clean or hashes["main"] != hashes["base"]):
            raise ReconciliationError(
                f"derived output must block and be recomputed from delivery sources: {relative_path}"
            )
        counts[classification] += 1
        rows.append(
            {
                "path": relative_path,
                "classification": classification,
                "derived": derived,
                "main_clean": main_clean,
                "sha256": hashes,
            }
        )

    if counts != EXPECTED_COUNTS:
        raise ReconciliationError(f"classification counts drifted: {counts}")
    return {
        "schema_version": 1,
        "decision_refs": ["D65-A", "D68"],
        "refs": refs,
        "main_root": str(main_root),
        "access_policy": {
            "git_objects": "immutable-full-refs-only",
            "main": "exact-path-status-and-sha256-only",
        },
        "derived_output_policy": {
            "exclude_classification": "matches-base",
            "requires": {"main_clean": True, "main_sha256": "equals-base"},
            "otherwise": "block-and-recompute-from-delivery-sources",
        },
        "counts": counts,
        "paths": rows,
    }


def _require_exact_keys(value: Any, keys: set[str], label: str) -> None:
    if type(value) is not dict or set(value) != keys:
        raise ReconciliationError(f"{label} has an invalid object shape")


def validate_shape(manifest: Any) -> None:
    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "decision_refs",
            "refs",
            "main_root",
            "access_policy",
            "derived_output_policy",
            "counts",
            "paths",
        },
        "manifest",
    )
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ReconciliationError("schema_version must be integer 1")
    if manifest["decision_refs"] != ["D65-A", "D68"]:
        raise ReconciliationError("decision_refs must be the exact ordered allowlist")
    if type(manifest["main_root"]) is not str:
        raise ReconciliationError("main_root must be a string")

    _require_exact_keys(manifest["refs"], {"base", "main", "delivery"}, "refs")
    for key, value in manifest["refs"].items():
        if type(value) is not str or not COMMIT_RE.fullmatch(value):
            raise ReconciliationError(f"refs.{key} must be a full immutable commit")
    _require_exact_keys(manifest["access_policy"], {"git_objects", "main"}, "access_policy")
    if any(type(value) is not str for value in manifest["access_policy"].values()):
        raise ReconciliationError("access_policy values must be strings")
    _require_exact_keys(
        manifest["derived_output_policy"],
        {"exclude_classification", "requires", "otherwise"},
        "derived_output_policy",
    )
    if type(manifest["derived_output_policy"]["exclude_classification"]) is not str:
        raise ReconciliationError("derived exclusion classification must be a string")
    if type(manifest["derived_output_policy"]["otherwise"]) is not str:
        raise ReconciliationError("derived fallback policy must be a string")
    requires = manifest["derived_output_policy"]["requires"]
    _require_exact_keys(requires, {"main_clean", "main_sha256"}, "derived requires")
    if type(requires["main_clean"]) is not bool or type(requires["main_sha256"]) is not str:
        raise ReconciliationError("derived requirements have invalid types")

    _require_exact_keys(manifest["counts"], set(EXPECTED_COUNTS), "counts")
    for key, value in manifest["counts"].items():
        if type(value) is not int:
            raise ReconciliationError(f"counts.{key} must be an integer")
    if type(manifest["paths"]) is not list:
        raise ReconciliationError("paths must be a list")
    seen: list[str] = []
    for index, row in enumerate(manifest["paths"]):
        _require_exact_keys(
            row,
            {"path", "classification", "derived", "main_clean", "sha256"},
            f"paths[{index}]",
        )
        if type(row["path"]) is not str or type(row["classification"]) is not str:
            raise ReconciliationError(f"paths[{index}] string fields have invalid types")
        if type(row["derived"]) is not bool or type(row["main_clean"]) is not bool:
            raise ReconciliationError(f"paths[{index}] boolean fields have invalid types")
        _require_exact_keys(row["sha256"], {"base", "main", "delivery"}, f"paths[{index}].sha256")
        for label, digest in row["sha256"].items():
            if type(digest) is not str or not SHA256_RE.fullmatch(digest):
                raise ReconciliationError(f"paths[{index}].sha256.{label} is invalid")
        seen.append(row["path"])
    if tuple(seen) != EXPECTED_PATHS:
        raise ReconciliationError("paths must equal the sorted exact allowlist")


def _canonical_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_manifest(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o644)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the canonical manifest")
    mode.add_argument("--check", action="store_true", help="verify the canonical manifest")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        expected = build_manifest()
        validate_shape(expected)
        canonical = _canonical_bytes(expected)
        if args.write:
            _write_manifest(args.manifest, canonical)
            print(f"d65-reconciliation: wrote {args.manifest} (8 conflict / 1 matches-delivery / 2 matches-base)")
            return 0
        actual_bytes = args.manifest.read_bytes()
        try:
            actual = json.loads(actual_bytes)
        except json.JSONDecodeError as exc:
            raise ReconciliationError(f"manifest is not valid JSON: {exc}") from exc
        validate_shape(actual)
        if actual != expected or actual_bytes != canonical:
            raise ReconciliationError("manifest differs from the sealed canonical snapshot")
        print("d65-reconciliation: OK (8 conflict / 1 matches-delivery / 2 matches-base)")
        return 0
    except (OSError, ReconciliationError) as exc:
        print(f"d65-reconciliation: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
