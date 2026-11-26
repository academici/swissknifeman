"""policy §5.2: one test per classifier row K1-K15 plus the named regressions."""

import pytest

from skm.modules.policy.domain.calls import (
    FileDelete,
    FileEdit,
    FileRead,
    FileWrite,
    RunCommand,
    ToolCall,
    WebAccess,
)
from skm.modules.policy.domain.classify import Classification, classify, parse_url
from skm.modules.policy.domain.operations import OperationName, PathOrigin, StaticPathFacts, TaskAuthority
from skm.modules.policy.domain.paths import PathRule, PathScope, ScopeRoots
from skm.modules.policy.domain.shell_words import simple_commands

WT = "/w/attempt/repo"
Op = OperationName


@pytest.fixture
def run(roots: ScopeRoots, facts: StaticPathFacts, empty_authority: TaskAuthority):
    def classify_call(
        call: ToolCall, authority: TaskAuthority = empty_authority, **changes
    ) -> Classification:
        used_facts = changes.get("facts", facts)
        words = simple_commands(call.command) if isinstance(call, RunCommand) else None
        return classify(
            call, roots=changes.get("roots", roots), facts=used_facts, authority=authority, words=words
        )

    return classify_call


def ops(found: Classification) -> set[OperationName]:
    return {hit.operation for hit in found.hits}


def sh(command: str) -> RunCommand:
    return RunCommand(command, WT)


def test_k1_git_internal_write(run) -> None:
    assert ops(run(FileWrite(f"{WT}/.git/config"))) == {Op.MODIFY_GIT_DIR}
    assert ops(run(sh("echo x > .git/hooks/pre-commit"))) == {Op.MODIFY_GIT_DIR}


def test_k2_write_inside_write_scope_or_undeclared(run, empty_authority: TaskAuthority) -> None:
    assert ops(run(FileEdit(f"{WT}/src/app.py"))) == {Op.MODIFY_WRITE_SET}
    scoped = TaskAuthority((PathRule(PathScope.WORKTREE, "src/**"),), (), frozenset(), frozenset())
    assert ops(run(FileWrite(f"{WT}/src/new.py"), scoped)) == {Op.MODIFY_WRITE_SET}


def test_k3_write_outside_write_scope(run) -> None:
    scoped = TaskAuthority((PathRule(PathScope.WORKTREE, "src/**", "main"),), (), frozenset(), frozenset())
    assert ops(run(FileWrite(f"{WT}/docs/x.md"), scoped)) == {Op.MODIFY_OUTSIDE_WRITE_SET}
    assert ops(run(sh("touch docs/y.md"), scoped)) == {Op.MODIFY_OUTSIDE_WRITE_SET}


def test_k4_deletions_by_origin(run) -> None:
    assert ops(run(FileDelete(f"{WT}/src/app.py"))) == {Op.DELETE_TRACKED}
    assert ops(run(sh("rm build/out.o build/tmp.log"))) == {Op.DELETE_OWN_UNTRACKED}
    assert ops(run(sh("unlink notes.txt"))) == {Op.DELETE_FOREIGN_UNTRACKED}
    assert ops(run(sh("rm -rf .git"))) == {Op.MODIFY_GIT_DIR}
    assert ops(run(sh("git rm src/util.py"))) == {Op.DELETE_TRACKED}
    assert ops(run(sh("git rm --cached src/util.py"))) == set()
    assert ops(run(sh("mv src/app.py build/"))) >= {Op.DELETE_TRACKED}
    assert ops(run(sh("rm gone.txt"))) == set()


def test_k4_glob_is_expanded_by_facts(run) -> None:
    found = run(sh("rm -rf build/*"))
    assert ops(found) == {Op.DELETE_OWN_UNTRACKED}
    assert {hit.subject for hit in found.hits} == {f"{WT}/build/out.o", f"{WT}/build/tmp.log"}


def test_k4_glob_too_wide_asks(run, facts: StaticPathFacts) -> None:
    narrow_facts = StaticPathFacts(facts.origins_by_path, facts.links, facts.home, max_glob_matches=1)
    found = run(sh("rm build/*"), facts=narrow_facts)
    assert ("glob_too_wide", "'build/*' expands to too many paths") in found.asks


def test_k5_find_delete_is_fail_closed(run) -> None:
    assert ops(run(sh("find . -name '*.pyc' -delete"))) == {Op.DELETE_TRACKED, Op.DELETE_FOREIGN_UNTRACKED}
    assert ops(run(sh("find . -exec rm {} +"))) == {Op.DELETE_TRACKED, Op.DELETE_FOREIGN_UNTRACKED}


def test_k6_write_heads(run) -> None:
    found = run(
        sh("cp a b/dest && tee log.txt && sed -i 's/a/b/' f.txt && echo x >> o.txt && chmod +x run.sh")
    )
    assert found.writes == (f"{WT}/b/dest", f"{WT}/log.txt", f"{WT}/f.txt", f"{WT}/o.txt", f"{WT}/run.sh")
    assert ops(found) == {Op.MODIFY_WRITE_SET}
    outside = run(sh("echo x > /etc/motd"))
    assert outside.writes == ("/etc/motd",)
    assert ops(outside) == set()


@pytest.mark.parametrize(
    "command",
    [
        "sed -i 's/a/b/' f.txt",
        "sed -i -es/a/b/ f.txt",
        "sed -i --exp=s/a/b/ f.txt",
        "sed -i --expression s/a/b/ f.txt",
        "sed -n -fscript.sed -i f.txt",
        "sed -ne s/a/b/p -i f.txt",
        "sed --in=.bak s/a/b/ f.txt",
        "sed -E -i s/a/b/ f.txt",
        "sed -ie s/a/b/ f.txt",
        "sed -l 40 -i s/a/b/ f.txt",
        "perl -pi -e 's/a/b/' f.txt",
        "perl -i -pe 's/a/b/' f.txt",
        "perl -i -p -es/a/b/ f.txt",
        "yq -i '.a = 1' f.txt",
        "yq --inplace=true '.a = 1' f.txt",
        "yq -i --from-file=edit.yq f.txt",
    ],
)
def test_in_place_editor_targets_in_every_spelling(run, command: str) -> None:
    # Attached or abbreviated script options once hid the edited file, so a write escaped F2.
    assert run(sh(command)).writes == (f"{WT}/f.txt",)


@pytest.mark.parametrize(
    ("command", "writes"),
    [
        ("cp -t /etc src/app.py", ("/etc",)),
        ("cp -t/etc src/app.py", ("/etc",)),
        ("cp --target=/etc src/app.py", ("/etc",)),
        ("cp -at /etc src/app.py", ("/etc",)),
        ("install -Dt /etc src/app.py", ("/etc",)),
        ("ln -st /etc src/app.py", ("/etc",)),
        ("cp --target-dir /etc src/app.py", ("/etc",)),
        ("cp -a src/app.py /etc/app.py", ("/etc/app.py",)),
        ("rsync -avt src/app.py /etc/app.py", ("/etc/app.py",)),
        ("chmod --ref=src/app.py run.sh other.sh", (f"{WT}/run.sh", f"{WT}/other.sh")),
        ("chmod 755 run.sh", (f"{WT}/run.sh",)),
    ],
)
def test_destination_options_in_every_spelling(run, command: str, writes: tuple[str, ...]) -> None:
    # An attached, clustered or abbreviated target directory once left the destination unseen by F2.
    assert run(sh(command)).writes == writes


@pytest.mark.parametrize("command", ["mv -t/tmp src/app.py", "mv --target=/tmp src/app.py"])
def test_a_move_with_any_target_spelling_deletes_its_sources(run, command: str) -> None:
    assert Op.DELETE_TRACKED in ops(run(sh(command)))


@pytest.mark.parametrize("command", ["sed -n s/a/b/p f.txt", "sed -es/i/x/ f.txt", "perl -ne print f.txt"])
def test_in_place_editors_without_in_place_write_nothing(run, command: str) -> None:
    assert run(sh(command)).writes == ()


def test_k7_git_guard(run) -> None:
    assert ops(run(sh("git push --force"))) == {Op.GIT_FORCE_PUSH}
    assert ops(run(sh("git push origin main"))) == {Op.GIT_PUSH}
    assert ops(run(sh("git reset --hard"))) == {Op.GIT_DISCARD}


@pytest.mark.parametrize(
    "command",
    [
        "git config user.name x",
        "git config --unset core.x",
        "git remote add up url",
        "git remote set-url origin url",
        "git worktree add ../x",
        "git update-index --skip-worktree a",
        "git replace a b",
        "git -c core.hooksPath=x commit -m m",
    ],
)
def test_k8_git_dir_changes(run, command: str) -> None:
    assert Op.MODIFY_GIT_DIR in ops(run(sh(command)))


@pytest.mark.parametrize(
    "command", ["git config --get user.name", "git config -l", "git config user.name", "git remote -v"]
)
def test_k8_reads_are_not_changes(run, command: str) -> None:
    assert Op.MODIFY_GIT_DIR not in ops(run(sh(command)))


def test_k9_regex_fallback_on_unsupported_line(
    roots: ScopeRoots, facts: StaticPathFacts, empty_authority
) -> None:
    found = classify(
        sh("for x in 1; do git push -f; done"),
        roots=roots,
        facts=facts,
        authority=empty_authority,
        words=None,
    )
    assert ops(found) == {Op.GIT_FORCE_PUSH, Op.GIT_PUSH}


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create -t x",
        "gh issue comment 1 -b x",
        "gh api -X POST repos/a/b",
        "gh api x -f a=1",
        "glab mr merge 3",
    ],
)
def test_k10_forge_writes(run, command: str) -> None:
    assert Op.FORGE_WRITE in ops(run(sh(command)))


@pytest.mark.parametrize(
    "command",
    [
        "npm publish",
        "twine upload dist/*",
        "cargo publish",
        "docker push img",
        "gh release create v1",
        "uv publish",
        "composer publish",
        "pub publish",
        "dart pub publish",
        "./mvnw clean deploy",
        "./gradlew :library:publishMavenPublicationToRegistryRepository",
        "dotnet nuget push library.nupkg",
        "dotnet nuget delete library 1.0.0",
    ],
)
def test_k11_publish(run, command: str) -> None:
    found = ops(run(sh(command)))
    assert Op.RELEASE_PUBLISH in found
    assert Op.FORGE_WRITE not in found


@pytest.mark.parametrize(
    "call",
    [
        RunCommand("cat ~/.ssh/id_rsa", WT),
        RunCommand("cat .env", WT),
        RunCommand("gpg -d secrets.gpg", WT),
        RunCommand("aws secretsmanager get-secret-value --secret-id x", WT),
        RunCommand("kubectl get secret x", WT),
        RunCommand("op read op://x", WT),
        FileRead("/home/dev/.aws/credentials"),
        FileRead(f"{WT}/deploy/server.pem"),
    ],
)
def test_k12_secrets(run, call: ToolCall) -> None:
    assert Op.SECRETS_ACCESS in ops(run(call))


@pytest.mark.parametrize(
    "command",
    ["cd ~/.ssh && cat config", "cd ~/.aws; grep key credentials", "pushd /home/dev/.kube; head config"],
)
def test_k12_a_bare_name_in_a_secret_directory_is_a_secret(run, command: str) -> None:
    assert Op.SECRETS_ACCESS in ops(run(sh(command)))


def test_k12_a_bare_name_elsewhere_is_no_secret(run) -> None:
    assert Op.SECRETS_ACCESS not in ops(run(sh("cd /home/dev && grep config notes.txt")))


@pytest.mark.parametrize(
    "command",
    ["cat ~/.netr?", "cat ~/.ss?/config", "cat ~/.config/gh/host?.yml", "cat .en?", "cat sub/.env*"],
)
def test_k12_a_glob_the_shell_expands_onto_a_secret_is_a_secret(run, command: str) -> None:
    assert Op.SECRETS_ACCESS in ops(run(sh(command)))


@pytest.mark.parametrize("command", ["cat *", "grep x *.json", "ls ~/*", "cat src/*.py"])
def test_k12_a_wide_glob_is_no_secret(run, command: str) -> None:
    assert Op.SECRETS_ACCESS not in ops(run(sh(command)))


def test_k12_example_env_is_not_a_secret(run) -> None:
    assert Op.SECRETS_ACCESS not in ops(run(sh("cat .env.example")))


@pytest.mark.parametrize(
    "command",
    [
        "docker ps",
        "podman run x",
        "DOCKER_HOST=tcp://x make",
        "curl --unix-socket /var/run/docker.sock x",
        "export DOCKER_HOST=x",
    ],
)
def test_k13_docker_socket(run, command: str) -> None:
    assert Op.DOCKER_SOCKET in ops(run(sh(command)))


@pytest.mark.parametrize(
    "command", ["psql -h db", "kubectl get pods", "ssh host", "terraform apply", "rsync -a x host:/y"]
)
def test_k14_external_services(run, command: str) -> None:
    assert Op.EXTERNAL_SERVICES in ops(run(sh(command)))


def test_k15_network_targets(run) -> None:
    assert {(t.host, t.port) for t in run(sh("curl https://example.com:8443/x")).network} == {
        ("example.com", 8443)
    }
    assert {t.host for t in run(sh("pip install requests")).network} == {"pypi.org", "files.pythonhosted.org"}
    assert {t.host for t in run(sh("npm ci")).network} == {"registry.npmjs.org"}
    assert {t.host for t in run(sh("apt-get install x")).network} == {None}
    assert {t.host for t in run(sh("git fetch origin")).network} == {"github.com"}
    assert {t.host for t in run(sh("git clone git@gitlab.com:a/b.git")).network} == {"gitlab.com"}
    assert {t.host for t in run(sh("gh pr view 1")).network} == {"api.github.com"}
    assert {t.host for t in run(sh("GH_HOST=ghe.corp gh pr view 1")).network} == {"ghe.corp"}
    assert {t.host for t in run(WebAccess("web.fetch", "http://a.example/x", None)).network} == {"a.example"}
    assert run(sh("ls")).network == ()


def test_abbreviated_git_discard_flags_are_discards(run) -> None:
    assert ops(run(sh("git reset --har"))) == {Op.GIT_DISCARD}
    assert ops(run(sh("git clean --for -d"))) == {Op.GIT_DISCARD}


def hosts(found: Classification) -> set[str | None]:
    return {target.host for target in found.network}


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("composer require vendor/package", {"packagist.org", "repo.packagist.org"}),
        ("pub get", {"pub.dev"}),
        ("dart pub add http", {"pub.dev"}),
        ("mvn clean install", {"repo.maven.apache.org", "plugins.gradle.org"}),
        ("./gradlew :library:dependencies", {"repo.maven.apache.org", "plugins.gradle.org"}),
        ("dotnet restore", {None}),
        ("dotnet add package Library", {None}),
    ],
)
def test_ecosystem_install_network_targets(run, command: str, expected: set[str | None]) -> None:
    assert hosts(run(sh(command))) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # R5: every destination is reported, not only the first URL
        ("curl https://pypi.org/simple evil.example", {"pypi.org", "evil.example"}),
        ("curl --url=https://evil.example https://pypi.org/simple", {"pypi.org", "evil.example"}),
        ("curl --url https://evil.example https://pypi.org/simple", {"pypi.org", "evil.example"}),
        ("curl -x evil.example:3128 https://pypi.org/simple", {"pypi.org", "evil.example"}),
        ("curl -sSLx evil.example https://pypi.org/simple", {"pypi.org", "evil.example"}),
        ("curl --socks5 evil.example:1080 https://pypi.org/simple", {"pypi.org", "evil.example"}),
        ("https_proxy=http://evil.example:8080 curl https://pypi.org/", {"pypi.org", "evil.example"}),
        (
            "env HTTPS_PROXY=evil.example pip install x",
            {"pypi.org", "files.pythonhosted.org", "evil.example"},
        ),
        ("wget https://pypi.org/x evil.example/y", {"pypi.org", "evil.example"}),
        ("curl --unknown-option evil.example https://pypi.org/", {"pypi.org", "evil.example"}),
        # an option that moves the destination out of the argv leaves it unresolved
        ("curl --resolve pypi.org:443:203.0.113.9 https://pypi.org/", {"pypi.org", None}),
        ("curl --connect-to pypi.org:443:evil.example:443 https://pypi.org/", {"pypi.org", None}),
        ("curl -K cfg https://pypi.org/", {"pypi.org", None}),
        ("wget --input=urls.txt https://pypi.org/", {"pypi.org", None}),
        ("wget -e use_proxy=on https://pypi.org/", {"pypi.org", None}),
        ('curl "$URL" https://pypi.org/', {"pypi.org", None}),
        # option values are no destinations
        ("curl -sSL -o out.html -H 'Accept: x' -d a=1 https://pypi.org/simple", {"pypi.org"}),
        ("curl -XPOST --data-raw x https://pypi.org/simple", {"pypi.org"}),
        ("wget -O out.html --header 'A: b' https://pypi.org/x", {"pypi.org"}),
        ("http POST pypi.org/x a=1 Accept:x", {"pypi.org"}),
        ("http --proxy=http:http://evil.example pypi.org/x", {"pypi.org", None}),
    ],
)
def test_one_allowed_url_hides_no_other_destination(run, command: str, expected: set[str | None]) -> None:
    assert hosts(run(sh(command))) == expected


def test_git_without_url_and_without_remotes_is_unresolved(run, roots: ScopeRoots) -> None:
    bare = ScopeRoots(
        roots.worktrees, roots.materials, roots.tmp, roots.home, roots.safe_dirs, roots.protected, frozenset()
    )
    assert {t.host for t in run(sh("git pull"), roots=bare).network} == {None}


def test_unresolved_targets_ask(run) -> None:
    found = run(sh("rm $X"))
    assert ops(found) == {Op.DELETE_TRACKED, Op.DELETE_FOREIGN_UNTRACKED}
    assert found.asks[0][0] == "unsupported_syntax"
    assert run(sh("cd $D && rm x")).asks[0][0] == "unsupported_syntax"


@pytest.mark.parametrize("command", ["touch ~root/x", "cd ~root && touch x", "cp a ~-"])
def test_a_tilde_naming_another_directory_is_unresolved(run, command: str) -> None:
    found = run(sh(command))
    assert not any("~" in path for path in found.writes)
    assert any(code == "unsupported_syntax" for code, _ in found.asks)


def test_cd_moves_relative_paths(run) -> None:
    assert run(sh("cd /etc && touch passwd")).writes == ("/etc/passwd",)


@pytest.mark.parametrize(
    "command",
    [
        # R2: a cd that may not move the shell leaves the directory unknown for what follows
        "ls | cd /etc; touch passwd",
        "ls |& cd /etc; touch passwd",
        "cd /etc & touch passwd",
        "true && cd /etc; touch passwd",
        "true || cd /etc && touch passwd",
        "env cd /etc; touch passwd",
        "ls | pushd /etc; touch passwd",
    ],
)
def test_a_cd_outside_the_shell_does_not_move_later_commands(run, command: str) -> None:
    found = run(sh(command))
    assert found.writes == ()
    assert ("unsupported_syntax", "target 'passwd' cannot be resolved before execution") in found.asks


def test_a_pipeline_cd_cannot_hide_a_deletion_outside_the_worktree(run) -> None:
    found = run(RunCommand(f"ls | cd {WT}/build; rm out.o", "/"))
    assert Op.DELETE_OWN_UNTRACKED not in ops(found)
    assert found.asks


@pytest.mark.parametrize(
    "command",
    [
        "env -C /etc /bin/rm -f passwd",
        "env --chdir=/etc /bin/rm passwd",
        "env --ch /etc rm passwd",
        "env -iC /etc touch passwd",
        "sudo -D /etc rm passwd",
        "env -C / env -C etc touch passwd",
    ],
)
def test_wrapper_directory_moves_the_wrapped_program(run, command: str) -> None:
    assert "/etc/passwd" in run(sh(command)).writes


@pytest.mark.parametrize(
    ("command", "target"),
    [
        ("env -C build -C . touch created.txt", f"{WT}/created.txt"),
        ("env --chdir=build --chdir=. touch created.txt", f"{WT}/created.txt"),
        ("env -C build env -C . touch created.txt", f"{WT}/build/created.txt"),
    ],
)
def test_only_the_last_directory_of_one_wrapper_counts(run, command: str, target: str) -> None:
    assert run(sh(command)).writes == (target,)


@pytest.mark.parametrize(
    "command", ["env -C $D -C build touch created.txt", "env --chdir=$D -C build touch created.txt"]
)
def test_a_later_directory_does_not_hide_an_opaque_one(run, command: str) -> None:
    found = run(sh(command))
    assert f"{WT}/build/created.txt" not in found.writes
    assert any(code == "unsupported_syntax" for code, _ in found.asks)


def test_wrapper_directory_does_not_move_the_shell_or_its_redirects(run) -> None:
    assert run(sh("env -C /etc touch a > out.txt")).writes == (f"{WT}/out.txt", "/etc/a")
    assert run(sh("env -C /etc true; touch x")).writes == (f"{WT}/x",)
    found = run(sh('env -C "$D" touch x'))
    assert found.writes == ()
    assert found.asks[0][0] == "unsupported_syntax"


def test_symlink_is_classified_by_its_target(run) -> None:
    found = run(FileWrite(f"{WT}/escape/passwd"))
    assert found.writes == ("/etc/passwd",)
    assert ops(found) == set()


def test_parse_url_forms() -> None:
    assert parse_url("https://user:pw@Host.Example:444/p") == ("host.example", 444)
    assert parse_url("http://[::1]/x") == ("::1", 80)
    assert parse_url("git@github.com:org/repo.git") == ("github.com", 22)
    assert parse_url("relative/path") is None


def test_unknown_origin_paths_fail_closed(run) -> None:
    found = ops(run(FileDelete(f"{WT}/unknown/file")))
    assert found == {Op.DELETE_TRACKED, Op.DELETE_FOREIGN_UNTRACKED}
    assert PathOrigin.ABSENT not in StaticPathFacts().origins("/x")
