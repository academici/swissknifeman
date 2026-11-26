"""Remote normalization, redaction, provider, endpoint (workspace §5.1, §4.3) and repository remote rules."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import RepositoryId, WorkspaceId
from skm.modules.workspace.domain.remote_url import (
    NormalizedRemote,
    RemoteEndpoint,
    normalize_remote,
    provider_of,
    redact_remote,
    remote_endpoint,
)
from skm.modules.workspace.domain.repository import (
    RepositoryProvider,
    add_remote,
    new_repository,
    set_primary,
)

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
REPO_ID = RepositoryId(UUID(int=1))
WS_ID = WorkspaceId(UUID(int=2))
_VECTORS = (
    Path(__file__).resolve().parents[4]
    / "tests/fixtures/corpus/examples"
    / "workspace"
    / "remote-normalization-vectors.json"
)
VECTORS: list[dict[str, Any]] = json.loads(_VECTORS.read_text(encoding="utf-8"))["vectors"]


def _ids() -> list[str]:
    return [repr(vector["input"]) for vector in VECTORS]


@pytest.mark.parametrize("vector", VECTORS, ids=_ids())
def test_vector_normalize(vector: dict[str, Any]) -> None:
    result = normalize_remote(vector["input"])
    assert (None if result is None else result.value) == vector["normalized"]


@pytest.mark.parametrize("vector", [v for v in VECTORS if "redacted" in v], ids=lambda v: repr(v["input"]))
def test_vector_redact(vector: dict[str, Any]) -> None:
    assert redact_remote(vector["input"]) == vector["redacted"]


@pytest.mark.parametrize("vector", VECTORS, ids=_ids())
def test_vector_provider(vector: dict[str, Any]) -> None:
    assert provider_of(normalize_remote(vector["input"])).value == vector["provider"]


def test_vectors_cover_every_provider_and_the_null_case() -> None:
    assert {v["provider"] for v in VECTORS} == {p.value for p in RepositoryProvider}
    assert any(v["normalized"] is None for v in VECTORS)


def test_redacted_remote_carries_no_credentials() -> None:
    assert "secret" not in redact_remote("https://user:secret@example.com/a/b")
    assert "token" not in redact_remote("https://token@example.com/a/b")


@pytest.mark.parametrize(
    ("url", "redacted"),
    [
        ("https://user:pa/ss@example.com/a/b", "https://example.com/a/b"),
        ("https://user:p@ss@example.com/a/b", "https://example.com/a/b"),
        ("https://user:p?s#s@example.com/a/b", "https://example.com/a/b"),
        ("https://to/ken@example.com:8443/a/b", "https://example.com:8443/a/b"),
        ("us@er@example.com:a/b.git", "example.com:a/b.git"),
    ],
)
def test_a_credential_with_separators_never_leaks_into_the_redacted_remote(url: str, redacted: str) -> None:
    assert redact_remote(url) == redacted


def test_normalized_remote_host_and_validation() -> None:
    assert NormalizedRemote("gitlab.example.com:8443/team/repo").host() == "gitlab.example.com:8443"
    for bad in ("", "nohost", "host/", "/path", "host/a b", "host/a\nb", "h/" + "x" * 2048):
        with pytest.raises(ValidationFailed) as err:
            NormalizedRemote(bad)
        assert err.value.code is ErrorCode.SCHEMA_INVALID


def test_overlong_remote_does_not_normalize() -> None:
    assert normalize_remote("https://example.com/" + "a" * 2048) is None


# --- endpoint: what the match key forgets (workspace §4.3) ---


def test_ssh_ports_share_a_match_key_but_not_an_endpoint() -> None:
    first = "ssh://git@code.example:2222/team/repo.git"
    second = "ssh://git@code.example:2200/team/repo.git"
    assert normalize_remote(first) == normalize_remote(second)
    assert remote_endpoint(first) != remote_endpoint(second)
    assert remote_endpoint(first) == RemoteEndpoint("ssh", "code.example", 2222, "team/repo")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:a/b.git", RemoteEndpoint("ssh", "github.com", 22, "a/b")),
        ("ssh://git@GitHub.com/a/b", RemoteEndpoint("ssh", "github.com", 22, "a/b")),
        ("git+ssh://github.com:22/a/b.git", RemoteEndpoint("ssh", "github.com", 22, "a/b")),
        ("https://user:pw@github.com/a/b.git", RemoteEndpoint("https", "github.com", 443, "a/b")),
        ("https://gitlab.example.com:8443/t/r", RemoteEndpoint("https", "gitlab.example.com", 8443, "t/r")),
        ("http://example.com/a/b", RemoteEndpoint("http", "example.com", 80, "a/b")),
        ("git://example.com/a/b", RemoteEndpoint("git", "example.com", 9418, "a/b")),
    ],
)
def test_endpoint_values(url: str, expected: RemoteEndpoint) -> None:
    assert remote_endpoint(url) == expected


def test_https_port_is_part_of_the_match_key_and_the_endpoint() -> None:
    assert normalize_remote("https://h.example:8443/a/b") != normalize_remote("https://h.example/a/b")


@pytest.mark.parametrize(
    "url",
    [
        "/srv/x.git",
        "file:///x/y",
        "",
        "https://example.com:abc/a/b",
        "https://example.com:0/a/b",
        "ssh://example.com:70000/a/b",
        "ftp://example.com/a/b",
    ],
)
def test_endpoint_is_never_guessed(url: str) -> None:
    assert remote_endpoint(url) is None


def test_endpoint_json_has_no_credentials_and_the_four_fields() -> None:
    endpoint = remote_endpoint("https://user:secret@example.com:8443/a/b.git")
    assert endpoint is not None
    document = endpoint.to_json()
    assert set(document) == {"transport", "hostname", "effective_port", "repository_path"}
    assert "secret" not in json.dumps(document)


# --- repository remote rules ---


def _repo(url: str | None = "git@github.com:a/b.git") -> Any:
    return new_repository(
        repository_id=REPO_ID, workspace_id=WS_ID, title=" Title ", remote_url=url, external_id=None, now=NOW
    )


def test_new_repository_normalizes_and_names_the_provider() -> None:
    repo = _repo()
    assert repo.title == "Title"
    assert repo.canonical_remote == NormalizedRemote("github.com/a/b")
    assert repo.provider is RepositoryProvider.GITHUB
    assert repo.row_version == 1


def test_local_repository_has_no_remote_and_no_provider() -> None:
    repo = _repo(None)
    assert repo.canonical_remote is None
    assert repo.provider is RepositoryProvider.NONE


@pytest.mark.parametrize("url", ["/srv/x.git", "file:///x", "", "plain"])
def test_new_repository_rejects_a_url_that_is_not_a_network_remote(url: str) -> None:
    with pytest.raises(ValidationFailed) as err:
        _repo(url)
    assert err.value.code is ErrorCode.SCHEMA_INVALID
    assert err.value.details == {"field": "remote_url", "reason": "not_a_network_remote"}


@pytest.mark.parametrize(
    ("title", "external"), [("", None), ("   ", None), ("x" * 201, None), ("ok", ""), ("ok", "x" * 201)]
)
def test_new_repository_bounds(title: str, external: str | None) -> None:
    with pytest.raises(ValidationFailed):
        new_repository(
            repository_id=REPO_ID,
            workspace_id=WS_ID,
            title=title,
            remote_url=None,
            external_id=external,
            now=NOW,
        )


def test_first_remote_becomes_primary_and_canonical() -> None:
    repo = _repo(None)
    result = add_remote(repo, (), "https://token@GitLab.com/g/p.git", make_primary=False)
    assert result.changed
    assert result.repository.canonical_remote == NormalizedRemote("gitlab.com/g/p")
    assert result.repository.provider is RepositoryProvider.GITLAB
    assert result.repository.row_version == 2
    (only,) = result.remotes
    assert only.is_primary
    assert only.display_url == "https://GitLab.com/g/p.git"


def test_second_remote_stays_secondary_and_make_primary_moves_the_primary() -> None:
    repo = _repo()
    first = add_remote(repo, (), "git@github.com:a/b.git", make_primary=False)
    assert first.repository == repo  # same canonical remote: nothing to save
    second = add_remote(first.repository, first.remotes, "https://codeberg.org/a/b", make_primary=False)
    assert [r.is_primary for r in second.remotes] == [True, False]
    assert second.repository.canonical_remote == NormalizedRemote("github.com/a/b")
    third = add_remote(second.repository, second.remotes, "https://gitlab.com/a/b", make_primary=True)
    assert [r.is_primary for r in third.remotes] == [False, False, True]
    assert third.repository.canonical_remote == NormalizedRemote("gitlab.com/a/b")
    assert third.repository.provider is RepositoryProvider.GITLAB


def test_duplicate_remote_is_a_no_op() -> None:
    repo = _repo()
    first = add_remote(repo, (), "git@github.com:a/b.git", make_primary=False)
    again = add_remote(first.repository, first.remotes, "https://github.com/a/b/", make_primary=True)
    assert not again.changed
    assert again.repository is first.repository
    assert again.remotes == first.remotes


def test_add_remote_rejects_a_local_path() -> None:
    with pytest.raises(ValidationFailed) as err:
        add_remote(_repo(), (), "/srv/x.git", make_primary=False)
    assert err.value.code is ErrorCode.SCHEMA_INVALID


def test_set_primary_keeps_exactly_one_primary_equal_to_canonical() -> None:
    repo = _repo()
    one = add_remote(repo, (), "git@github.com:a/b.git", make_primary=False)
    two = add_remote(one.repository, one.remotes, "https://gitlab.com/a/b", make_primary=False)
    moved = set_primary(two.repository, two.remotes, NormalizedRemote("gitlab.com/a/b"))
    assert moved.changed
    assert [r.is_primary for r in moved.remotes] == [False, True]
    assert moved.repository.canonical_remote == NormalizedRemote("gitlab.com/a/b")
    same = set_primary(moved.repository, moved.remotes, NormalizedRemote("gitlab.com/a/b"))
    assert not same.changed
    with pytest.raises(NotFound):
        set_primary(moved.repository, moved.remotes, NormalizedRemote("example.com/x/y"))
