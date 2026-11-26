from pathlib import Path

import pytest

from skm.platform.fs.atomic_write import UnsafePathError
from skm.platform.fs.safe_paths import is_within, safe_join


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("", "empty"),
        ("a\0b", "nul"),
        ("/etc/passwd", "absolute"),
        ("C:/file", "absolute"),
        ("C:file", "absolute"),
        (r"\\host\share\file", "absolute"),
        (r"\rooted", "absolute"),
        ("../file", "escapes_root"),
        ("a/../../file", "escapes_root"),
        ("../root/file", "escapes_root"),
    ],
)
def test_untrusted_path_rejected(tmp_path: Path, path: str, reason: str) -> None:
    with pytest.raises(UnsafePathError) as caught:
        safe_join(tmp_path, path)
    assert caught.value.reason == reason


def test_ordinary_contained_paths_and_dot_components(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    assert safe_join(tmp_path, "a/../new") == tmp_path / "a/../new"
    assert safe_join(tmp_path, "./new") == tmp_path / "new"
    assert safe_join(tmp_path, ".") == tmp_path
    assert is_within(tmp_path, tmp_path / "a/../new")
    assert not is_within(tmp_path, tmp_path.with_name(tmp_path.name + "-other") / "x")


@pytest.mark.parametrize("inside", [False, True])
@pytest.mark.parametrize("allow", [False, True])
def test_symlink_policy_always_checks_resolved_containment(tmp_path: Path, inside: bool, allow: bool) -> None:
    root = tmp_path / "root"
    root.mkdir()
    destination = root / "inside" if inside else tmp_path / "outside"
    destination.mkdir()
    (root / "link").symlink_to(destination, target_is_directory=True)
    if allow and inside:
        assert safe_join(root, "link/new", allow_symlinks=True) == root / "link/new"
    else:
        with pytest.raises(UnsafePathError) as caught:
            safe_join(root, "link/new", allow_symlinks=allow)
        assert caught.value.reason == ("escapes_root" if allow else "symlink")


def test_symlink_dotdot_and_dangling_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(tmp_path / "missing")
    for path in ("link/file", "link/../root/file"):
        with pytest.raises(UnsafePathError):
            safe_join(root, path)
    with pytest.raises(UnsafePathError, match="escapes_root"):
        safe_join(root, "link/file", allow_symlinks=True)
