"""Operation classifier (policy §5.2, rows K1-K15).

``classify`` maps one tool call onto operations of the G14 table plus the facts ``check_tool_call`` needs:
local write targets (F2 for paths outside the worktree), path candidates (P0), network targets (N1) and the
reasons to ask (an unresolved target, a glob that expands too wide, an unknown working directory). It is a
best-effort preflight on top of the supported shell subset; filesystem and network boundaries are enforced
by the isolation profile, never by this text analysis (§§5.2, 5.2a).
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from . import command_classes as cc
from .calls import FileDelete, FileEdit, FileRead, FileWrite, RunCommand, ToolCall, WebAccess
from .git_guard import fallback_hits, judge, split_globals
from .glob_overlap import glob_overlap
from .network import FORGE_API_HOSTS, REGISTRY_HOSTS
from .operations import OperationHit, OperationName, PathFacts, PathOrigin, TaskAuthority
from .paths import PathScope, ScopeRoots, classify_path, glob_match
from .repo_commands import forge_write, gh_api_read, git_dir_change, remote_operand
from .shell_words import ShellWord, SimpleCommand

__all__ = ["Classification", "NetworkTarget", "base_cwd", "classify", "classify_call", "parse_url"]

_DISCARD = OperationName.GIT_DISCARD
_GIT_OPERATIONS = {"push-force": OperationName.GIT_FORCE_PUSH, "git-push": OperationName.GIT_PUSH}
_FALLBACK_OPERATIONS = {**_GIT_OPERATIONS, "push-force-with-lease": OperationName.GIT_FORCE_PUSH}
_ORIGIN_OPERATIONS = {
    PathOrigin.TRACKED: OperationName.DELETE_TRACKED,
    PathOrigin.OWN_UNTRACKED: OperationName.DELETE_OWN_UNTRACKED,
    PathOrigin.IGNORED: OperationName.DELETE_OWN_UNTRACKED,
    PathOrigin.FOREIGN_UNTRACKED: OperationName.DELETE_FOREIGN_UNTRACKED,
    PathOrigin.GIT_INTERNAL: OperationName.MODIFY_GIT_DIR,
}
_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_SCP_RE = re.compile(r"^(?:[A-Za-z0-9._-]+@)?([A-Za-z0-9.-]+\.[A-Za-z]{2,}|[A-Za-z0-9-]+):(?!/)")
_DEFAULT_PORTS = {"http": 80, "https": 443, "ftp": 21, "ssh": 22, "git": 9418, "ws": 80, "wss": 443}
_VALUE_OPTIONS: dict[str, frozenset[str]] = {
    "cp": frozenset({"-t", "--target-directory", "-S", "--suffix"}),
    "mv": frozenset({"-t", "--target-directory", "-S", "--suffix"}),
    "install": frozenset(
        {"-t", "--target-directory", "-m", "--mode", "-o", "--owner", "-g", "--group", "-S"}
    ),
    "ln": frozenset({"-t", "--target-directory", "-S", "--suffix"}),
    "rsync": frozenset({"-e", "--rsh", "--exclude", "--include", "--filter", "-f"}),
    "chmod": frozenset({"--reference"}),
    "chown": frozenset({"--reference"}),
    "chgrp": frozenset({"--reference"}),
    "truncate": frozenset({"-s", "--size", "-r", "--reference"}),
    "mkdir": frozenset({"-m", "--mode"}),
    "touch": frozenset({"-d", "--date", "-t", "-r", "--reference"}),
    "tee": frozenset(),
}
_MOVES = frozenset({"cd", "pushd", "popd"})
# a directory change is certain only in the shell itself: not in a pipeline, a background job or a branch
_CERTAIN_BEFORE = frozenset({"", ";", "&", "\n"})
_CERTAIN_AFTER = frozenset({"", ";", "&&", "\n"})
_PROXY_VARIABLES = frozenset({"http_proxy", "https_proxy", "all_proxy", "ftp_proxy"})
_HTTPIE_HEADS = frozenset({"http", "https", "xh"})
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"})


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


_HTTPIE_OPTIONS = (
    _words(
        "-a --auth -A --auth-type -o --output -p --print -P --history-print -s --style --session"
        " --session-read-only --pretty --format-options --response-charset --response-mime --verify --cert"
        " --cert-key --cert-key-pass --ssl --ciphers --timeout --max-redirects --max-headers --boundary"
        " --default-scheme --bearer --interface"
    ),
    frozenset[str](),
    _words("--proxy --resolve --unix-socket"),
)
# URL clients: (options taking a value, options whose value is a destination, options that hide it)
_CLIENT_OPTIONS: dict[str, tuple[frozenset[str], frozenset[str], frozenset[str]]] = {
    "curl": (
        _words(
            "-A -b -c -C -d -D -e -E -F -H -m -o -P -Q -r -t -T -u -U -w -X -y -Y -z --abstract-unix-socket"
            " --alt-svc --aws-sigv4 --cacert --capath --cert --cert-type --ciphers --connect-timeout"
            " --continue-at --cookie --cookie-jar --create-file-mode --crlfile --curves --data --data-ascii"
            " --data-binary --data-raw --data-urlencode --delegation --dns-interface --dns-ipv4-addr"
            " --dns-ipv6-addr --dump-header --ech --egd-file --engine --etag-compare --etag-save"
            " --expect100-timeout --form --form-string --ftp-account --ftp-alternative-to-user --ftp-method"
            " --ftp-port --ftp-ssl-ccc-mode --happy-eyeballs-timeout-ms --haproxy-clientip --header"
            " --hostpubmd5 --hostpubsha256 --hsts --interface --ip-tos --json --keepalive-time --key"
            " --key-type --krb --libcurl --limit-rate --local-port --login-options --mail-auth --mail-from"
            " --mail-rcpt --max-filesize --max-redirs --max-time --netrc-file --noproxy --oauth2-bearer"
            " --output --output-dir --parallel-max --pass --pinnedpubkey --proto --proto-default"
            " --proto-redir --proxy-cacert --proxy-capath --proxy-cert --proxy-cert-type --proxy-ciphers"
            " --proxy-crlfile --proxy-header --proxy-key --proxy-key-type --proxy-pass --proxy-pinnedpubkey"
            " --proxy-service-name --proxy-tls13-ciphers --proxy-tlsauthtype --proxy-tlspassword"
            " --proxy-tlsuser --proxy-user --pubkey --quote --random-file --range --rate --referer --request"
            " --request-target --retry --retry-delay --retry-max-time --sasl-authzid --service-name"
            " --socks5-gssapi-service --speed-limit --speed-time --stderr --telnet-option --tftp-blksize"
            " --time-cond --tls-max --tls13-ciphers --tlsauthtype --tlspassword --tlsuser --trace"
            " --trace-ascii --trace-config --unix-socket --upload-file --url-query --user --user-agent"
            " --variable --write-out"
        ),
        _words(
            "-x --url --proxy --preproxy --doh-url --ipfs-gateway --socks4 --socks4a --socks5"
            " --socks5-hostname --proxy1.0"
        ),
        _words("-K --config --resolve --connect-to --dns-servers"),
    ),
    "wget": (
        _words(
            "-o -a -t -O -T -w -Q -P -l -A -R -D -I -X -U --output-file --append-output --tries"
            " --output-document --timeout --dns-timeout --connect-timeout --read-timeout --wait --waitretry"
            " --quota --bind-address --limit-rate --directory-prefix --cut-dirs --default-page --http-user"
            " --http-password --header --max-redirect --proxy-user --proxy-password --referer --save-cookies"
            " --load-cookies --post-data --post-file --method --body-data --body-file --user-agent --user"
            " --password --ftp-user --ftp-password --level --accept --reject --accept-regex --reject-regex"
            " --domains --exclude-domains --include-directories --exclude-directories --certificate"
            " --certificate-type --private-key --private-key-type --ca-certificate --ca-directory --crl-file"
            " --secure-protocol --ciphers --hsts-file --warc-file --warc-header --warc-max-size"
            " --restrict-file-names --prefer-family --retry-on-http-error --local-encoding --remote-encoding"
            " --rejected-log --report-speed --progress --pinnedpubkey --random-file --egd-file"
        ),
        frozenset[str](),
        _words("-i -e -B --input-file --execute --base --config --use-askpass"),
    ),
    "http": _HTTPIE_OPTIONS,
    "https": _HTTPIE_OPTIONS,
    "xh": _HTTPIE_OPTIONS,
}


@dataclass(frozen=True, slots=True)
class NetworkTarget:
    host: str | None  # None: the destination cannot be determined
    port: int | None
    subject: str


@dataclass(frozen=True, slots=True)
class Classification:
    hits: tuple[OperationHit, ...] = ()
    writes: tuple[str, ...] = ()  # resolved local write targets
    paths: tuple[str, ...] = ()  # resolved path candidates (P0)
    network: tuple[NetworkTarget, ...] = ()
    asks: tuple[tuple[str, str], ...] = ()  # (rule, reason)


def parse_url(url: str) -> tuple[str, int | None] | None:
    """Host and effective port of a URL (``scheme://[user@]host[:port]/…``) or an scp-like git address."""
    match = _URL_RE.match(url)
    if match is None:
        scp = _SCP_RE.match(url)
        return None if scp is None else (scp.group(1).lower(), 22)
    scheme = url[: match.end() - 3].lower()
    authority = url[match.end() :].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    authority = authority.rsplit("@", 1)[-1]
    if authority.startswith("["):
        host, _, rest = authority[1:].partition("]")
        port_text = rest[1:] if rest.startswith(":") else ""
    else:
        host, _, port_text = authority.partition(":")
    if not host:
        return None
    port = int(port_text) if port_text.isdigit() else _DEFAULT_PORTS.get(scheme)
    return host.lower(), port


def base_cwd(roots: ScopeRoots) -> str:
    """Directory a relative file path of a non-shell tool is resolved against: the single worktree, else
    ``/`` (a relative path then falls outside every scope and is refused)."""
    return next(iter(roots.worktrees.values())) if len(roots.worktrees) == 1 else "/"


def _long_option(name: str, value_options: frozenset[str]) -> str:
    """The value option a GNU-style ``--name`` abbreviates, else ``name`` itself; an ambiguous prefix makes
    the program fail, so taking it for a value option can only report more."""
    if name in value_options or len(name) <= 2:
        return name
    matches = [option for option in value_options if option.startswith("--") and option.startswith(name)]
    return matches[0] if len(matches) == 1 else name


def _options_split(
    words: Iterable[ShellWord], value_options: frozenset[str]
) -> tuple[list[ShellWord], dict[str, str]]:
    """Operands and options of a getopt-style argv. Short clusters are split per letter (``-at DIR``,
    ``-tDIR``) and long options may be abbreviated (``--target=DIR``); keys are canonical option names."""
    operands: list[ShellWord] = []
    options: dict[str, str] = {}
    pending: str | None = None
    literal = False
    for word in words:
        value = word.value
        if pending is not None:
            options[pending] = value
            pending = None
        elif literal or not value.startswith("-") or value == "-":
            operands.append(word)
        elif value == "--":
            literal = True
        elif value.startswith("--"):
            name, sep, item = value.partition("=")
            name = _long_option(name, value_options)
            if not sep and name in value_options:
                pending = name
            else:
                options[name] = item
        else:
            for position, letter in enumerate(value[1:], start=1):
                option = "-" + letter
                if option in value_options:
                    rest = value[position + 1 :]
                    if rest:
                        options[option] = rest
                    else:
                        pending = option
                    break
                options[option] = ""
    return operands, options


@dataclass(slots=True)
class _Collector:
    roots: ScopeRoots
    facts: PathFacts
    authority: TaskAuthority
    hits: list[OperationHit] = field(default_factory=list[OperationHit])
    writes: list[str] = field(default_factory=list[str])
    paths: list[str] = field(default_factory=list[str])
    network: list[NetworkTarget] = field(default_factory=list[NetworkTarget])
    asks: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])

    def result(self) -> Classification:
        return Classification(
            tuple(dict.fromkeys(self.hits)),
            tuple(dict.fromkeys(self.writes)),
            tuple(dict.fromkeys(self.paths)),
            tuple(dict.fromkeys(self.network)),
            tuple(dict.fromkeys(self.asks)),
        )

    def hit(self, operation: OperationName, subject: str, detail: str, path: str | None = None) -> None:
        scoped = None if path is None else classify_path(path, self.roots)
        self.hits.append(OperationHit(operation, subject, detail, scoped))

    def write(self, path: str, detail: str) -> None:
        self.writes.append(path)
        self.paths.append(path)
        scoped = classify_path(path, self.roots)
        self._secret(path, path, detail)
        if scoped.scope is not PathScope.WORKTREE:
            return
        if ".git" in scoped.relative.split("/") or PathOrigin.GIT_INTERNAL in self.facts.origins(path):
            self.hit(OperationName.MODIFY_GIT_DIR, path, f"K1 {detail}", path)
            return
        scope = self.authority.write_scope
        inside = scope is None or any(rule.matches(scoped) for rule in scope)
        operation = OperationName.MODIFY_WRITE_SET if inside else OperationName.MODIFY_OUTSIDE_WRITE_SET
        self.hit(operation, path, f"{'K2' if inside else 'K3'} {detail}", path)

    def delete(self, path: str, detail: str) -> None:
        self.writes.append(path)
        self.paths.append(path)
        self._secret(path, path, detail)
        scoped = classify_path(path, self.roots)
        if scoped.scope is PathScope.WORKTREE and ".git" in scoped.relative.split("/"):
            self.hit(OperationName.MODIFY_GIT_DIR, path, f"K4 {detail}", path)
            return
        for origin in sorted(self.facts.origins(path)):
            operation = _ORIGIN_OPERATIONS.get(origin)
            if operation is not None:
                self.hit(operation, path, f"K4 {detail} ({origin})", path)

    def unresolved_delete(self, subject: str) -> None:
        self.hit(OperationName.DELETE_TRACKED, subject, "K5 unresolved deletion target")
        self.hit(OperationName.DELETE_FOREIGN_UNTRACKED, subject, "K5 unresolved deletion target")

    def read(self, path: str, detail: str) -> None:
        self.paths.append(path)
        self._secret(path, path, detail)

    def _secret(self, path: str, subject: str, detail: str) -> None:
        if _secret_path(path, self.roots.home):
            self.hit(OperationName.SECRETS_ACCESS, subject, f"K12 {detail}")


def _secret_glob(pattern: str, name: str, home: str | None) -> bool:
    """A glob the shell may expand onto a secret: ``~/.netr?`` reads ``~/.netrc``. A shell wildcard never
    expands onto a dotfile, so only the dot-leading basename secrets are matched against a glob basename;
    ``*.json`` stays no secret although ``credentials.json`` is one."""
    if any(glob_overlap(name, glob) for glob in cc.SECRET_BASENAME_GLOBS if glob.startswith(".")):
        return True
    if home is None:
        return False
    prefix = home.rstrip("/") + "/"
    return any(glob_overlap(pattern, glob, prefix=prefix) for glob in cc.SECRET_HOME_GLOBS)


def _secret_path(path: str, home: str | None) -> bool:
    name = posixpath.basename(path)
    if name not in cc.SECRET_BASENAME_EXCEPTIONS and any(
        glob_match(glob, name) for glob in cc.SECRET_BASENAME_GLOBS
    ):
        return True
    if any(char in path for char in "*?[") and _secret_glob(path, name, home):
        return True
    if home is None:
        return False
    home = home.rstrip("/")
    if not path.startswith(home + "/"):
        return False
    relative = path[len(home) + 1 :]
    return any(glob_match(glob, relative) for glob in cc.SECRET_HOME_GLOBS)


class _Shell:
    """Classifies the simple commands of one shell line, tracking ``cd``/``pushd``/``popd``."""

    def __init__(self, collector: _Collector, cwd: str) -> None:
        self.c = collector
        self.cwd: str | None = cwd
        self.stack: list[str | None] = []
        self.git_hits = False

    def resolve(self, word: ShellWord) -> str | None:
        value = word.value
        if word.opaque:
            return None
        if self.cwd is None and not value.startswith(("/", "~")):
            return None
        return self.c.facts.resolve(value, self.cwd or "/")

    def unresolved(self, subject: str) -> None:
        self.c.asks.append(("unsupported_syntax", f"target {subject!r} cannot be resolved before execution"))

    def run(self, commands: tuple[SimpleCommand, ...]) -> None:
        # per depth: working directory, directory stack, separator before the next command
        contexts: dict[int, tuple[str | None, list[str | None], str]] = {0: (self.cwd, [], "")}
        for command in commands:
            depth = command.depth
            if depth not in contexts:
                parent = max(level for level in contexts if level < depth)
                cwd, stack, _ = contexts[parent]
                contexts[depth] = (cwd, stack.copy(), "")
            self.cwd, self.stack, before = contexts[depth]
            contexts = {level: state for level, state in contexts.items() if level <= depth}
            self.command(command)
            self._move(command, before)
            contexts[depth] = (self.cwd, self.stack, command.connector)

    def _move(self, command: SimpleCommand, before: str) -> None:
        head = command.head
        if head in _MOVES and (
            command.wrappers or before not in _CERTAIN_BEFORE or command.connector not in _CERTAIN_AFTER
        ):
            # a pipeline member, a background job, a branch of && / || or a wrapped program: whether the
            # shell's own directory changes is unknown, so relative paths after it are unresolved
            self.stack = list[str | None]([None] * (len(self.stack) + (head == "pushd")))
            self.cwd = None
            return
        if head in {"cd", "pushd"}:
            if head == "pushd":
                self.stack.append(self.cwd)
            args = [word for word in command.words[1:] if not word.value.startswith("-")]
            target = args[0] if args else ShellWord(self.c.roots.home or "", opaque=self.c.roots.home is None)
            self.cwd = None if target.value == "-" else self.resolve(target)
            if self.cwd is not None:
                self.c.paths.append(self.cwd)
        elif head == "popd":
            self.cwd = self.stack.pop() if self.stack else None

    def command(self, command: SimpleCommand) -> None:
        for target in command.redirect_targets:
            self._write(ShellWord(target), f"redirect of {command.head}")
        for target in command.read_targets:
            path = self.resolve(ShellWord(target))
            if path is not None:
                self.c.read(path, "redirect")
        outer = self.cwd
        for directory in command.chdirs:  # ``env -C dir``: the program, not the shell, runs there
            self.cwd = self.resolve(directory)
            if self.cwd is None:
                self.unresolved(directory.value or f"directory of {command.head}")
                break
            self.c.paths.append(self.cwd)
        try:
            self._program(command)
        finally:
            self.cwd = outer

    def _program(self, command: SimpleCommand) -> None:
        if not command.words:
            self._assignments(command.assignments, command)
            return
        head = command.head
        self._arguments(command)
        self._assignments(command.assignments, command)
        if head in {"export", "declare", "typeset", "readonly", "local"}:
            self._assignments(tuple(word.value for word in command.words[1:]), command)
        self._deletes(command)
        self._writes(command)
        if head == "git":
            self._git(command)
        self._services(command)
        self._network(command)

    def _arguments(self, command: SimpleCommand) -> None:
        for word in command.words[1:]:
            value = word.value
            if word.opaque:
                self.unresolved(value or command.head)
                continue
            if value.startswith("-") or not value:
                continue
            if any(socket in value for socket in cc.DOCKER_SOCKETS):
                self.c.hit(OperationName.DOCKER_SOCKET, value, "K13 container engine socket")
            if "/" in value or value.startswith(("~", ".")) or _secret_path(value, None):
                path = self.resolve(word)
                if path is not None:
                    self.c.read(path, f"argument of {command.head}")
            elif self.cwd is not None:
                # a bare name is read only as a secret: ``cd ~/.ssh && cat config`` reads ~/.ssh/config
                path = self.resolve(word)
                if path is not None and _secret_path(path, self.c.roots.home):
                    self.c.read(path, f"argument of {command.head}")

    def _assignments(self, assignments: tuple[str, ...], command: SimpleCommand) -> None:
        for assignment in assignments:
            name = assignment.split("=", 1)[0]
            if name in cc.DOCKER_HOST_VARIABLES:
                self.c.hit(
                    OperationName.DOCKER_SOCKET, assignment, f"K13 {name} for {command.head or 'shell'}"
                )

    def _deletes(self, command: SimpleCommand) -> None:
        head, words = command.head, command.words
        operands: list[ShellWord] = []
        if head in cc.DELETE_HEADS:
            operands, _ = _options_split(words[1:], frozenset({"-n", "--iterations", "-s", "--size"}))
        elif head == "git":
            _, sub, args = split_globals(command.argv[1:])
            if sub == "rm" and "--cached" not in args:
                operands, _ = _options_split(words[len(words) - len(args) :], frozenset[str]())
        elif head == "mv":
            moved, options = _options_split(words[1:], _VALUE_OPTIONS["mv"])
            target = options.get("-t", options.get("--target-directory"))
            operands = moved if target is not None else moved[:-1]
        elif head == "find":
            argv = command.argv
            nested = {
                posixpath.basename(argv[index + 1])
                for index, word in enumerate(argv[:-1])
                if word in {"-exec", "-execdir", "-ok", "-okdir"}
            }
            if "-delete" in argv or nested & cc.DELETE_HEADS:
                self.c.unresolved_delete(command.text or "find")
        for word in operands:
            self._delete(word, head)

    def _delete(self, word: ShellWord, head: str) -> None:
        if word.value == "{}":
            return
        if word.opaque:
            self.c.unresolved_delete(word.value or head)
            self.unresolved(word.value or head)
            return
        if word.glob:
            if self.cwd is None and not word.value.startswith("/"):
                self.unresolved(word.value)
                return
            expanded = self.c.facts.expand(word.value, self.cwd or "/")
            if expanded is None:
                self.c.asks.append(("glob_too_wide", f"{word.value!r} expands to too many paths"))
                return
            for path in expanded:
                self.c.delete(self.c.facts.resolve(path, self.cwd or "/"), f"{head} {word.value}")
            return
        path = self.resolve(word)
        if path is None:
            self.unresolved(word.value)
            return
        self.c.delete(path, head)

    def _write(self, word: ShellWord, detail: str) -> None:
        if word.opaque or (word.glob and self.cwd is None):
            self.unresolved(word.value or detail)
            return
        path = self.resolve(word)
        if path is None:
            self.unresolved(word.value)
            return
        self.c.write(path, detail)

    def _writes(self, command: SimpleCommand) -> None:
        for word in _write_operands(command):
            self._write(word, f"{command.head} operand")

    def _git(self, command: SimpleCommand) -> None:
        for violation in judge(command.argv):
            self.git_hits = True
            operation = _GIT_OPERATIONS.get(violation.id, _DISCARD)
            self.c.hit(operation, violation.command, f"K7 git guard {violation.id}")
        config, sub, args = split_globals(command.argv[1:])
        if "core.hookspath" in config or git_dir_change(sub, args):
            self.c.hit(OperationName.MODIFY_GIT_DIR, " ".join(command.argv), f"K8 git {sub or ''}".strip())

    def _services(self, command: SimpleCommand) -> None:
        head = command.head
        positionals = tuple(word.value for word in command.words[1:] if not word.value.startswith("-"))
        argv = command.argv
        text = " ".join(argv)
        if head == "gh" and positionals[:1] == ("api",) and not gh_api_read(argv[1:]):
            self.c.hit(OperationName.FORGE_WRITE, text, "K10 gh api write")
        published = any(
            cc.package_rule_matches(head, program, rule, positionals) for program, rule in cc.PUBLISH_RULES
        )
        if published:
            self.c.hit(OperationName.RELEASE_PUBLISH, text, "K11 publish")
        elif forge_write(head, positionals):
            self.c.hit(OperationName.FORGE_WRITE, text, f"K10 {head} write")
        if any(
            head == program and cc.rule_matches(rule, positionals) for program, rule in cc.SECRET_COMMANDS
        ):
            self.c.hit(OperationName.SECRETS_ACCESS, text, "K12 secret manager")
        decrypt = cc.SECRET_DECRYPT_FLAGS.get(head)
        if decrypt is not None and decrypt & set(argv[1:]):
            self.c.hit(OperationName.SECRETS_ACCESS, text, "K12 decryption")
        if head == "aws" and positionals[:2] == ("ssm", "get-parameter") and "--with-decryption" in argv:
            self.c.hit(OperationName.SECRETS_ACCESS, text, "K12 decrypted parameter")
        if head in cc.DOCKER_HEADS:
            self.c.hit(OperationName.DOCKER_SOCKET, text, "K13 container engine")
        if head in cc.EXTERNAL_SERVICE_HEADS:
            self.c.hit(OperationName.EXTERNAL_SERVICES, text, "K14 external service client")
        if head == "rsync" and any(remote_operand(value) for value in positionals):
            self.c.hit(OperationName.EXTERNAL_SERVICES, text, "K14 rsync to a remote host")

    def _network(self, command: SimpleCommand) -> None:
        head = command.head
        argv = command.argv
        positionals = tuple(word.value for word in command.words[1:] if not word.value.startswith("-"))
        text = " ".join(argv)
        found = len(self.c.network)
        if head in _CLIENT_OPTIONS:
            self._client_targets(command, text)
        elif head in cc.NETWORK_HEADS:
            self._socket_targets(positionals, text)
        for program, rule, family in cc.INSTALL_RULES:
            if cc.package_rule_matches(head, program, rule, positionals):
                hosts = REGISTRY_HOSTS.get(family, ())
                if not hosts:
                    self.c.network.append(NetworkTarget(None, None, text))
                self.c.network.extend(NetworkTarget(host, 443, text) for host in hosts)
                self.c.network.extend(
                    NetworkTarget(parsed[0], parsed[1], text)
                    for value in positionals
                    if "://" in value and (parsed := parse_url(value)) is not None
                )
                break
        if head == "git":
            _, sub, args = split_globals(argv[1:])
            if sub in cc.GIT_NETWORK_SUBCOMMANDS or (sub == "submodule" and "update" in args):
                self._git_targets(tuple(arg for arg in args if not arg.startswith("-")), text)
        if head in FORGE_API_HOSTS:
            variable = "GH_HOST" if head == "gh" else "GITLAB_HOST"
            override = next(
                (item.split("=", 1)[1] for item in command.assignments if item.startswith(variable + "=")),
                None,
            )
            self.c.network.append(NetworkTarget(override or FORGE_API_HOSTS[head], 443, text))
        if len(self.c.network) > found:  # a proxy variable sends the traffic of the command elsewhere
            self.c.network.extend(
                _destination(ShellWord(assignment.split("=", 1)[1]), text)
                for assignment in command.assignments
                if assignment.split("=", 1)[0].lower() in _PROXY_VARIABLES
            )

    def _client_targets(self, command: SimpleCommand, text: str) -> None:
        """Every destination of a URL client: each operand (a bare ``host/path`` is a URL to curl and wget),
        each URL option (``--url``, ``--proxy``…); an option that moves the destination out of the argv
        (``--config``, ``--resolve``, ``wget -i``) leaves it unresolved. One allowed URL hides nothing."""
        head = command.head
        values, urls, hidden = _CLIENT_OPTIONS[head]
        words = command.words[1:]
        operands: list[ShellWord] = []
        destinations: list[ShellWord] = []
        unresolved = False
        literal = False
        index = 0
        while index < len(words):
            word = words[index]
            index += 1
            if literal or not word.value.startswith("-") or word.value == "-":
                operands.append(word)
                continue
            if word.value == "--":
                literal = True
                continue
            option, attached = _client_option(word.value, values | urls | hidden, urls | hidden)
            if not option:
                continue
            if attached is None:
                argument = words[index] if index < len(words) else ShellWord("", opaque=True)
                index += 1
            else:
                argument = ShellWord(attached, word.opaque)
            if option in hidden or option.startswith("--expand-"):
                unresolved = True
            elif option in urls:
                destinations.append(argument)
        if head in _HTTPIE_HEADS:  # http [METHOD] URL [REQUEST_ITEM…]: items are no destinations
            if len(operands) > 1 and operands[0].value.upper() in _HTTP_METHODS:
                operands = operands[1:]
            operands = operands[:1]
        destinations.extend(operands)
        if unresolved or not destinations:
            self.c.network.append(NetworkTarget(None, None, text))
        self.c.network.extend(_destination(word, text) for word in destinations)

    def _socket_targets(self, positionals: tuple[str, ...], text: str) -> None:
        found: list[tuple[str, int | None]] = [
            parsed for value in positionals if (parsed := parse_url(value)) is not None and "://" in value
        ]
        if not found and positionals:
            first, rest = positionals[0], positionals[1:]
            port = int(rest[0]) if rest and rest[0].isdigit() else None
            found = [(first.lower(), port)]
        if not found:
            self.c.network.append(NetworkTarget(None, None, text))
        self.c.network.extend(NetworkTarget(host, port, text) for host, port in found)

    def _git_targets(self, positionals: tuple[str, ...], text: str) -> None:
        found = [parsed for value in positionals if (parsed := parse_url(value)) is not None]
        if found:
            self.c.network.extend(NetworkTarget(host, port, text) for host, port in found)
            return
        remotes = sorted(self.c.roots.remote_hosts)
        if not remotes:
            self.c.network.append(NetworkTarget(None, None, text))
        self.c.network.extend(NetworkTarget(host, None, text) for host in remotes)


def _client_option(value: str, takes_value: frozenset[str], first: frozenset[str]) -> tuple[str, str | None]:
    """``(option, attached value)`` of a client word that takes a value (``""``: a flag). A long name that
    abbreviates a destination option of ``first`` (wget and httpie accept abbreviations) counts as that
    option; an unknown option consumes nothing, so its value is judged as a destination."""
    if value.startswith("--"):
        name, sep, rest = value.partition("=")
        if name not in takes_value and not name.startswith("--expand-"):
            name = next((option for option in sorted(first) if len(name) > 2 and option.startswith(name)), "")
            if not name:
                return "", None
        return name, rest if sep else None
    for index, letter in enumerate(value[1:], start=2):
        if "-" + letter in takes_value:
            return "-" + letter, value[index:] or None
    return "", None


def _destination(word: ShellWord, text: str) -> NetworkTarget:
    """A URL or a bare ``host[:port][/path]`` (curl and wget add ``http://``); unknown when unparsable."""
    value = word.value
    parsed = None if word.opaque or not value else parse_url(value if "://" in value else "http://" + value)
    return NetworkTarget(None, None, text) if parsed is None else NetworkTarget(parsed[0], parsed[1], text)


@dataclass(frozen=True, slots=True)
class _EditorSyntax:
    """How one in-place editor spells its options: short letters whose value is attached or the next word,
    letters that swallow the rest of their cluster, and long options that carry the edit script."""

    in_place: str  # the short letter of in-place editing; it swallows an attached backup suffix
    script_letters: str  # the script (or script file) is attached or the next word
    value_letters: str  # another value, attached or the next word
    rest_letters: str  # an optional value attached to the letter, never the next word
    in_place_long: tuple[str, ...]
    script_long: tuple[str, ...]
    value_long: tuple[str, ...]
    abbreviates: bool  # getopt_long accepts unambiguous prefixes of long options


_EDITORS: dict[str, _EditorSyntax] = {
    "sed": _EditorSyntax(
        "i", "ef", "l", "", ("--in-place",), ("--expression", "--file"), ("--line-length",), abbreviates=True
    ),
    "perl": _EditorSyntax("i", "eE", "", "lIMmxCdD0", (), (), (), abbreviates=False),
    "yq": _EditorSyntax(
        "i",
        "",
        "oIp",
        "",
        ("--inplace",),
        ("--from-file",),
        ("--output-format", "--indent"),
        abbreviates=False,
    ),
}


def _long_named(word: str, options: tuple[str, ...], *, abbreviates: bool) -> bool:
    name = word.split("=", 1)[0]
    return any(
        name == option or (abbreviates and len(name) > 2 and option.startswith(name)) for option in options
    )


def _in_place(command: SimpleCommand) -> list[ShellWord]:
    """Files an in-place ``sed``/``perl``/``yq`` call rewrites; the first operand is the script unless an
    option supplied it. Unknown spellings err towards reporting more operands, never fewer."""
    syntax = _EDITORS[command.head]
    words = command.words[1:]
    in_place = script_given = False
    operands: list[ShellWord] = []
    index = 0
    while index < len(words):
        value = words[index].value
        if value == "--":
            operands.extend(words[index + 1 :])
            break
        if value.startswith("--"):
            takes_next = "=" not in value
            if _long_named(value, syntax.in_place_long, abbreviates=syntax.abbreviates):
                in_place = True
            elif _long_named(value, syntax.script_long, abbreviates=syntax.abbreviates):
                script_given = True
                index += takes_next
            elif _long_named(value, syntax.value_long, abbreviates=syntax.abbreviates):
                index += takes_next
        elif value.startswith("-") and value != "-":
            letters = value[1:]
            for position, letter in enumerate(letters):
                last = position == len(letters) - 1
                if letter == syntax.in_place:
                    in_place = True
                    break
                if letter in syntax.script_letters:
                    script_given = True
                    index += last
                    break
                if letter in syntax.value_letters:
                    index += last
                    break
                if letter in syntax.rest_letters:
                    break
        else:
            operands.append(words[index])
        index += 1
    if not in_place:
        return []
    return operands if script_given else operands[1:]


def _write_operands(command: SimpleCommand) -> list[ShellWord]:
    head = command.head
    if head in cc.IN_PLACE_EDITORS:
        return _in_place(command)
    if head not in cc.WRITE_HEADS:
        return []
    operands, options = _options_split(command.words[1:], _VALUE_OPTIONS.get(head, frozenset[str]()))
    if head in {"cp", "mv", "install", "ln", "rsync"}:
        target = None if head == "rsync" else options.get("-t", options.get("--target-directory"))
        if target is not None:
            return [ShellWord(target)]
        if len(operands) < 2:
            return []
        destination = operands[-1]
        return [] if head == "rsync" and remote_operand(destination.value) else [destination]
    if head in {"chmod", "chown", "chgrp"} and "--reference" not in options:
        return operands[1:]
    return operands


def _web(call: WebAccess, collector: _Collector) -> None:
    if call.tool != "web.fetch":
        return
    parsed = None if call.url is None else parse_url(call.url)
    host, port = (None, None) if parsed is None else parsed
    collector.network.append(NetworkTarget(host, port, call.url or ""))


def classify(
    call: ToolCall,
    *,
    roots: ScopeRoots,
    facts: PathFacts,
    authority: TaskAuthority,
    words: tuple[SimpleCommand, ...] | None,
) -> Classification:
    """Operations and facts of one call; ``words`` is the parse of a ``RunCommand`` (``None``:
    unsupported)."""
    collector = _Collector(roots, facts, authority)
    if isinstance(call, (FileRead, FileWrite, FileEdit, FileDelete)):
        path = facts.resolve(call.path, base_cwd(roots))
        if isinstance(call, FileRead):
            collector.read(path, "read")
        elif isinstance(call, FileDelete):
            collector.delete(path, "delete")
        else:
            collector.write(path, "write" if isinstance(call, FileWrite) else "edit")
    elif isinstance(call, RunCommand):
        cwd = facts.resolve(call.cwd, "/")
        collector.paths.append(cwd)
        shell = _Shell(collector, cwd)
        if words is not None:
            shell.run(words)
        if words is None or not shell.git_hits:
            for rule in fallback_hits(call.command):
                operation = _FALLBACK_OPERATIONS.get(rule.id, _DISCARD)
                collector.hit(operation, call.command, f"K9 regex fallback {rule.id}")
    elif isinstance(call, WebAccess):
        _web(call, collector)
    return collector.result()


def classify_call(
    call: ToolCall,
    *,
    roots: ScopeRoots,
    facts: PathFacts,
    authority: TaskAuthority,
    words: tuple[SimpleCommand, ...] | None,
) -> tuple[OperationHit, ...]:
    """The operation hits of §5.2 (``classify`` also returns the facts the checks need)."""
    return classify(call, roots=roots, facts=facts, authority=authority, words=words).hits
