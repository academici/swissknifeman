"""Byte-path round trips, typed identities, immutable refs and concurrent snapshot barriers."""

import hashlib
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.adapters.git import fingerprint
from skm.adapters.git.commit import ExcludeRules, GitOutputSealer, snapshot_commit
from skm.adapters.git.fingerprint import candidate, output_digest, path_fingerprint
from skm.adapters.git.status import (
    decode_path,
    display_path,
    encode_path,
    parse_porcelain,
    prune_stubs,
    tree_entries,
)
from skm.kernel.errors import SkmError
from skm.kernel.ids import RepositoryId
from skm.modules.execution.domain.output import ChangedPath, OutputMount, manifest_digest


@given(
    st.binary(min_size=1, max_size=80).filter(
        lambda p: b"/" not in p and b"\0" not in p and p not in {b".", b".."}
    )
)
def test_raw_path_encoding_is_reversible(raw):
    encoded = encode_path(raw)
    assert decode_path(encoded) == raw
    assert "=" not in encoded


@pytest.mark.parametrize(
    "raw", [b"tab\tname", b"line\nname", b"nonutf8-\xff", "é".encode(), "e\u0301".encode()]
)
def test_raw_snapshot_roundtrip(repository, tmp_path, raw):
    root, git, base = repository
    path = os.fsencode(root) + b"/" + raw
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o644)
    os.write(fd, b"raw\r\n\x00bytes")
    os.close(fd)
    snap = snapshot_commit(git, root, base, state_dir=tmp_path / "snapshots", message="raw snapshot\n")
    assert raw in tree_entries(git, root, snap.commit)
    assert path_fingerprint(root, raw, git=git) == tree_entries(git, root, snap.commit)[raw]
    assert (root / ".git/index").is_file()


def test_rename_copy_porcelain_keeps_both_byte_names():
    records = parse_porcelain(b"R  new\tname\0old\nname\0C  copy\xff\0source\xff\0?? extra\0")
    assert {(p.path, p.old_path) for p in records} == {
        (b"new\tname", b"old\nname"),
        (b"copy\xff", b"source\xff"),
        (b"extra", None),
    }
    with pytest.raises(ValueError, match="relative Git byte path"):
        parse_porcelain(b"R  target\0")


def test_filters_attributes_and_symlinks_do_not_transform_raw_bytes(repository, tmp_path):
    root, git, base = repository
    (root / ".gitattributes").write_text("*.txt text eol=lf filter=unknown\n")
    raw = b"literal\r\nbytes\x00"
    (root / "file.txt").write_bytes(raw)
    os.symlink(b"outside-\xff", os.fsencode(root / "link"))
    snap = snapshot_commit(git, root, base, state_dir=tmp_path / "state", message="raw bytes\n")
    entries = tree_entries(git, root, snap.commit)
    assert (
        entries[b"file.txt"]
        == "100644 "
        + hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False).hexdigest()
    )
    link_oid = entries[b"link"].split(" ")[1]
    assert git.run_bytes(root, ["cat-file", "blob", link_oid]).stdout == b"outside-\xff"


def test_seal_excludes_preserves_baseline_and_is_create_only(repository, tmp_path):
    root, git, base = repository
    (root / ".skm").mkdir()
    (root / ".skm/materials").write_text("private material")
    (root / ".runtime").write_text("runtime cache")
    (root / "file.txt").write_text("task bytes\n")
    sealer = GitOutputSealer(git, state_dir=tmp_path / "state")
    kwargs = {
        "attempt_id": str(uuid4()),
        "output_no": 1,
        "mount": "main",
        "repository_id": uuid4(),
        "baseline": base,
        "write_scope": ["file.txt"],
        "exclude": ExcludeRules(runtime_artifacts=(".runtime",)),
    }
    first = sealer.seal(root, **kwargs)
    assert first == sealer.seal(root, **kwargs)
    assert {p.path for p in first.changed_paths} == {"file.txt"}
    assert {p.path for p in first.excluded_paths} == {".skm/materials", ".runtime"}
    assert first.tree_digest != manifest_digest(first)
    (root / "file.txt").write_text("different bytes")
    with pytest.raises(SkmError, match="immutable ref"):
        sealer.seal(root, **kwargs)
    ref = f"refs/skm/outputs/{kwargs['attempt_id']}/1"
    assert git.run(root, ["rev-parse", ref]).stdout.strip() == first.mounts[0].head_commit
    patch = sealer.patch(root, first)
    assert b"+task bytes" in patch
    assert b"private material" not in patch


def test_noop_reuses_prior_commit(repository, tmp_path):
    root, git, base = repository
    snap = snapshot_commit(git, root, base, state_dir=tmp_path / "state", message="no change\n")
    assert snap.commit == base
    assert not snap.patch


@pytest.mark.parametrize(
    "identity", ["repository_id", "mount", "base_commit", "head_commit", "tree_sha", "object_format"]
)
def test_output_digest_binds_every_mount_identity(identity):
    mount = OutputMount("main", RepositoryId(uuid4()), "sha1", "1" * 40, "2" * 40, "3" * 40)
    path = ChangedPath("main", "a\tb\nc", encode_path(b"a\tb\nc"), "added", None, None, "100644 " + "4" * 40)
    original = output_digest((mount,), (path,))
    if identity == "object_format":
        modified = replace(
            mount, object_format="sha256", base_commit="1" * 64, head_commit="2" * 64, tree_sha="3" * 64
        )
        paths = (replace(path, fingerprint="100644 " + "4" * 64),)
    elif identity == "mount":
        modified = replace(mount, mount="other")
        paths = (replace(path, mount="other"),)
    else:
        modified = replace(
            mount, **{identity: RepositoryId(uuid4()) if identity == "repository_id" else "5" * 40}
        )
        paths = (path,)
    assert original != output_digest((modified,), paths)


def test_digest_no_unicode_or_encoding_collisions():
    mount = OutputMount("main", RepositoryId(uuid4()), "sha1", "1" * 40, "2" * 40, "3" * 40)
    paths = [b"tab\t", b"new\nline", b"a\xff", b"a\\xff", "é".encode(), "e\u0301".encode()]
    digests = {
        output_digest(
            (mount,),
            (
                ChangedPath(
                    "main", display_path(raw), encode_path(raw), "added", None, None, "100644 " + "4" * 40
                ),
            ),
        )
        for raw in paths
    }
    assert len(digests) == len(paths)
    with pytest.raises(ValueError, match="v2"):
        output_digest((mount,), (), algorithm="skm-output-v1")
    with pytest.raises(ValueError, match="mismatch"):
        output_digest(
            (mount,),
            (ChangedPath("main", "wrong", encode_path(b"right"), "added", None, None, "100644 " + "4" * 40),),
        )
    path = ChangedPath("main", "name", encode_path(b"name"), "added", None, None, "100644 " + "4" * 40)
    with pytest.raises(ValueError, match="duplicate"):
        output_digest((mount,), (path, path))


@pytest.mark.parametrize("mutation", ["editor", "rename", "index", "config", "gitdir", "commondir"])
def test_snapshot_barriers_reject_concurrent_user_mutation(repository, tmp_path, monkeypatch, mutation):
    root, git, base = repository
    original = fingerprint.path_fingerprint
    fired = False
    index = (root / ".git/index").read_bytes()

    def barrier(directory, raw, **kwargs):
        nonlocal fired
        result = original(directory, raw, **kwargs)
        if not fired:
            fired = True
            if mutation == "editor":
                (root / "file.txt").write_bytes(b"IDE edit")
            elif mutation == "rename":
                (root / "file.txt").rename(root / "renamed")
            elif mutation == "index":
                (root / ".git/index").write_bytes(index + b"parallel index mutation")
            elif mutation == "config":
                with (root / ".git/config").open("a") as stream:
                    stream.write('\n[filter "evil"]\nclean = touch forbidden\n')
            elif mutation == "gitdir":
                (root / ".git").rename(root / ".git-old")
                (root / ".git").mkdir()
            else:
                (root / ".git/commondir").write_text(str(tmp_path / "missing"))
        return result

    monkeypatch.setattr(fingerprint, "path_fingerprint", barrier)
    with pytest.raises((SkmError, ValueError, FileNotFoundError)):
        snapshot_commit(git, root, base, state_dir=tmp_path / "state", message="must reject\n")
    assert fired
    if mutation == "editor":
        assert (root / "file.txt").read_bytes() == b"IDE edit"
    if mutation == "rename":
        assert (root / "renamed").read_bytes() == b"initial\nsecond\n"
    if mutation == "index":
        assert (root / ".git/index").read_bytes() == index + b"parallel index mutation"


@pytest.mark.parametrize(
    "directive",
    [
        '[filter "canary"]\nclean = touch CANARY',
        "[core]\nfsmonitor = touch CANARY",
        "[include]\npath = hostile",
        "[credential]\nhelper = !touch CANARY",
        '[url "https://x"]\ninsteadOf = https://safe',
    ],
)
def test_untrusted_config_never_spawns_canary(repository, tmp_path, monkeypatch, directive):
    root, git, base = repository
    with (root / ".git/config").open("a") as stream:
        stream.write("\n" + directive + "\n")
    calls = []
    monkeypatch.setattr(git, "_execute", lambda *a, **k: calls.append(a))
    with pytest.raises(SkmError):
        candidate(root, (b"file.txt",), git=git)
    with pytest.raises(SkmError):
        snapshot_commit(git, root, base, state_dir=tmp_path / "state", message="no process\n")
    assert not calls
    assert not (root / "CANARY").exists()


def test_provider_stubs_pruned_only_with_exact_safe_shape(repository):
    root, git, _ = repository
    (root / ".provider").mkdir()
    stub = root / ".provider/stub"
    stub.touch(mode=0o444)
    real = root / ".provider/config"
    real.write_text("real config")
    real.chmod(0o444)
    prune_stubs(git, root, (".provider/stub", ".provider/config"))
    assert not stub.exists()
    assert real.read_text() == "real config"


def test_nested_repository_and_gitlink_rejected_before_snapshot(repository, tmp_path):
    root, git, base = repository
    nested = root / "nested"
    nested.mkdir()
    git.run(nested, ["init"])
    with pytest.raises(ValueError, match="nested"):
        snapshot_commit(git, root, base, state_dir=tmp_path / "state", message="reject\n")
    assert (nested / ".git/config").is_file()


def test_submodule_gitlink_rejects_before_object_writes(repository, tmp_path, monkeypatch):
    from .conftest import AUTHOR

    root, git, base = repository
    git.run(root, ["update-index", "--add", "--cacheinfo", "160000", base, "submodule"])
    git.run_bytes(root, ["commit", "-m", "gitlink"], env=AUTHOR)
    run = git.run_bytes

    def no_hash(cwd, args, **kwargs):
        assert "hash-object" not in args
        return run(cwd, args, **kwargs)

    monkeypatch.setattr(git, "run_bytes", no_hash)
    with pytest.raises(ValueError, match="submodule"):
        snapshot_commit(git, root, base, state_dir=tmp_path / "state", message="reject\n")


def test_scope_change_between_fence_and_snapshot_creates_no_output_ref(repository, tmp_path, monkeypatch):
    import skm.adapters.git.commit as sealing

    root, git, base = repository
    original = sealing.snapshot_commit

    def barrier(*args, **kwargs):
        (root / "outside.txt").write_text("IDE changes after first fence")
        return original(*args, **kwargs)

    monkeypatch.setattr(sealing, "snapshot_commit", barrier)
    with pytest.raises(SkmError, match="scope"):
        GitOutputSealer(git, state_dir=tmp_path / "state").seal(
            root,
            attempt_id="attempt",
            output_no=1,
            mount="main",
            repository_id=RepositoryId(uuid4()),
            baseline=base,
            write_scope=["file.txt"],
        )
    assert not git.run(root, ["for-each-ref", "refs/skm/outputs"]).stdout
    assert (root / "outside.txt").read_text() == "IDE changes after first fence"
