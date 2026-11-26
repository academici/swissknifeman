"""Data of the operation classifier (policy §5.2, rows K4-K15).

Rules match positional prefixes, or individual goals for Maven and Gradle. An empty prefix matches any
invocation of the program. Matching by basename classifies conservatively but never proves the identity
of a binary (§5.2a).
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CARRIER_HEADS",
    "DELETE_HEADS",
    "DOCKER_HEADS",
    "DOCKER_SOCKETS",
    "EXTERNAL_SERVICE_HEADS",
    "FORGE_GH_NOUNS",
    "FORGE_GH_VERBS",
    "FORGE_GLAB_NOUNS",
    "FORGE_GLAB_VERBS",
    "GIT_NETWORK_SUBCOMMANDS",
    "INLINE_FLAGS",
    "INSTALL_RULES",
    "NETWORK_HEADS",
    "PROJECTION_CARRIER_HEADS",
    "PUBLISH_RULES",
    "SECRET_BASENAME_EXCEPTIONS",
    "SECRET_BASENAME_GLOBS",
    "SECRET_COMMANDS",
    "SECRET_HOME_GLOBS",
    "WRITE_HEADS",
]

DELETE_HEADS: Final = frozenset({"rm", "rmdir", "unlink", "shred"})
# Heads whose operands are written (K6); cp/mv/install/ln/rsync write their destination only.
WRITE_HEADS: Final = frozenset(
    {"tee", "cp", "mv", "install", "ln", "rsync", "touch", "truncate", "mkdir", "chmod", "chown", "chgrp"}
)
IN_PLACE_EDITORS: Final = frozenset({"sed", "perl", "yq"})

FORGE_GH_NOUNS: Final = frozenset(
    {
        "pr",
        "issue",
        "repo",
        "gist",
        "label",
        "secret",
        "variable",
        "workflow",
        "run",
        "cache",
        "ruleset",
        "project",
        "ssh-key",
        "gpg-key",
    }
)
FORGE_GH_VERBS: Final = frozenset(
    {
        "create",
        "edit",
        "close",
        "reopen",
        "merge",
        "comment",
        "review",
        "delete",
        "ready",
        "lock",
        "unlock",
        "transfer",
        "pin",
        "unpin",
        "develop",
        "fork",
        "rename",
        "archive",
        "unarchive",
        "sync",
        "set",
        "remove",
        "add",
        "enable",
        "disable",
        "rerun",
        "cancel",
        "run",
        "link",
        "unlink",
        "mark-template",
        "copy",
    }
)
FORGE_GLAB_NOUNS: Final = frozenset({"mr", "issue", "release", "repo", "snippet", "variable", "ci"})
FORGE_GLAB_VERBS: Final = frozenset(
    {
        "create",
        "update",
        "close",
        "reopen",
        "merge",
        "note",
        "delete",
        "approve",
        "revoke",
        "rebase",
        "upload",
        "set",
        "retry",
        "cancel",
        "run",
    }
)
GH_API_READ_METHODS: Final = frozenset({"GET", "HEAD"})
GH_API_FIELD_FLAGS: Final = frozenset({"-f", "-F", "--field", "--raw-field", "--input"})

type _Prefix = tuple[str | frozenset[str], ...]
type Rule = tuple[str, _Prefix]


def _any(*words: str) -> frozenset[str]:
    return frozenset(words)


PUBLISH_RULES: Final[tuple[Rule, ...]] = (
    ("npm", ("publish",)),
    ("pnpm", ("publish",)),
    ("yarn", ("publish",)),
    ("npm", ("unpublish",)),
    ("npm", ("dist-tag", _any("add", "rm"))),
    ("twine", ("upload",)),
    ("cargo", (_any("publish", "yank", "owner"),)),
    ("poetry", ("publish",)),
    ("uv", ("publish",)),
    ("flit", ("publish",)),
    ("hatch", ("publish",)),
    ("gem", (_any("push", "yank"),)),
    ("composer", ("publish",)),
    ("pub", ("publish",)),
    ("dart", ("pub", "publish")),
    ("flutter", ("pub", "publish")),
    ("docker", ("push",)),
    ("podman", ("push",)),
    ("helm", ("push",)),
    ("dotnet", ("nuget", _any("push", "delete"))),
    ("mvn", (_any("deploy", "deploy:deploy", "deploy:deploy-file"),)),
    ("gradle", ("publish",)),
    ("gh", ("release", _any("create", "upload", "edit", "delete"))),
    ("glab", ("release", _any("create", "upload", "delete"))),
)

SECRET_HOME_GLOBS: Final = (
    ".ssh/**",
    ".aws/**",
    ".azure/**",
    ".config/gcloud/**",
    ".kube/**",
    ".docker/config.json",
    ".gnupg/**",
    ".password-store/**",
    ".config/gh/hosts.yml",
    ".netrc",
    ".pgpass",
    ".git-credentials",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials",
    ".cargo/credentials.toml",
)
SECRET_BASENAME_GLOBS: Final = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "credentials.json",
    "secrets.*",
)
SECRET_BASENAME_EXCEPTIONS: Final = frozenset({".env.example", ".env.sample", ".env.template"})
SECRET_COMMANDS: Final[tuple[Rule, ...]] = (
    ("pass", ()),
    ("gopass", ("show",)),
    ("op", (_any("read", "inject", "run"),)),
    ("op", ("item", "get")),
    ("bw", ("get",)),
    ("vault", (_any("read", "kv", "login", "token"),)),
    ("security", (_any("find-generic-password", "find-internet-password", "dump-keychain"),)),
    ("aws", ("secretsmanager", "get-secret-value")),
    ("gcloud", ("secrets", "versions", "access")),
    ("kubectl", ("get", _any("secret", "secrets"))),
)
# Programs whose decrypting flag reveals a secret: gpg -d, age -d, sops -d / exec-env / exec-file.
SECRET_DECRYPT_FLAGS: Final = {
    "gpg": frozenset({"-d", "--decrypt"}),
    "age": frozenset({"-d", "--decrypt"}),
    "sops": frozenset({"-d", "--decrypt", "exec-env", "exec-file"}),
}

DOCKER_HEADS: Final = frozenset(
    {"docker", "docker-compose", "podman", "podman-compose", "nerdctl", "buildah", "ctr", "crictl"}
)
DOCKER_SOCKETS: Final = ("docker.sock", "podman.sock", "containerd.sock")
DOCKER_HOST_VARIABLES: Final = frozenset({"DOCKER_HOST", "CONTAINER_HOST"})

EXTERNAL_SERVICE_HEADS: Final = frozenset(
    {
        "psql",
        "pg_dump",
        "pg_restore",
        "pg_dumpall",
        "mysql",
        "mysqldump",
        "mariadb",
        "sqlcmd",
        "redis-cli",
        "mongosh",
        "mongo",
        "cqlsh",
        "kubectl",
        "helm",
        "terraform",
        "tofu",
        "pulumi",
        "aws",
        "gcloud",
        "az",
        "doctl",
        "flyctl",
        "heroku",
        "vercel",
        "netlify",
        "ansible",
        "ansible-playbook",
        "ssh",
        "scp",
        "sftp",
    }
)

NETWORK_HEADS: Final = frozenset(
    {"curl", "wget", "http", "https", "xh", "nc", "ncat", "netcat", "telnet", "ftp"}
)
# (program, positional prefix) → registry family of REGISTRY_HOSTS; family "" means the host is unknown.
INSTALL_RULES: Final[tuple[tuple[str, _Prefix, str], ...]] = (
    ("pip", (_any("install", "download"),), "python"),
    ("pip3", (_any("install", "download"),), "python"),
    ("uv", ("pip", "install"), "python"),
    ("uv", (_any("add", "sync", "lock"),), "python"),
    ("poetry", (_any("add", "install", "lock", "update"),), "python"),
    ("pipx", ("install",), "python"),
    ("npm", (_any("install", "i", "add", "ci", "update"),), "node"),
    ("pnpm", (_any("install", "i", "add", "ci", "update"),), "node"),
    ("yarn", (_any("add", "install"),), "node"),
    ("npx", (), "node"),
    (
        "composer",
        (_any("install", "i", "update", "u", "upgrade", "require", "reinstall", "create-project", "global"),),
        "php",
    ),
    ("cargo", (_any("add", "install", "fetch", "update"),), "cargo"),
    ("go", (_any("get", "install"),), "go"),
    ("go", ("mod", "download"), "go"),
    ("gem", ("install",), "ruby"),
    ("bundle", ("install",), "ruby"),
    ("brew", ("install",), "brew"),
    ("pub", (_any("get", "upgrade", "downgrade", "add", "global"),), "dart"),
    ("dart", ("pub", _any("get", "upgrade", "downgrade", "add", "global")), "dart"),
    ("flutter", ("pub", _any("get", "upgrade", "downgrade", "add", "global")), "dart"),
    ("mvn", (_any("install", "package", "verify", "dependency:resolve", "dependency:go-offline"),), "jvm"),
    ("gradle", (_any("build", "assemble", "dependencies", "dependencyInsight"),), "jvm"),
    # NuGet feeds are configurable and have no registry family in this vocabulary.
    ("dotnet", ("restore",), ""),
    ("dotnet", ("add", "package"), ""),
    ("dotnet", ("package", "add"), ""),
    ("dotnet", ("tool", _any("install", "restore", "update")), ""),
    ("dotnet", ("workload", _any("install", "restore", "update")), ""),
    ("apt", ("install",), ""),
    ("apt-get", ("install",), ""),
    ("dnf", ("install",), ""),
    ("yum", ("install",), ""),
    ("apk", ("add",), ""),
    ("zypper", ("install",), ""),
    ("pacman", ("-S",), ""),
)
GIT_NETWORK_SUBCOMMANDS: Final = frozenset({"clone", "fetch", "pull", "ls-remote"})

# Heads whose own arguments may carry code (C3/C7 also search their raw text; port of CARRIER_RE).
CARRIER_HEADS: Final = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "csh",
        "eval",
        "exec",
        "xargs",
        "node",
        "deno",
        "bun",
        "perl",
        "ruby",
        "php",
        "lua",
        "env",
        "nohup",
        "timeout",
        "nice",
        "setsid",
        "watch",
        "su",
        "runuser",
        "script",
        "parallel",
        "ssh",
    }
)
# Native allow rules cannot express the policy checks on these commands' operands.
PROJECTION_CARRIER_HEADS: Final = (
    CARRIER_HEADS
    | NETWORK_HEADS
    | DELETE_HEADS
    | WRITE_HEADS
    | IN_PLACE_EDITORS
    | frozenset(
        {
            "ag", "cd", "chroot", "chrt", "command", "date", "file", "find", "fish", "hostname",
            "ionice", "popd", "pushd", "rg", "sort", "stdbuf", "time", "tree", "uniq", "xxd",
        }
    )
)  # fmt: skip

INLINE_FLAGS: Final = {
    "python": frozenset({"-c", "-"}),
    "node": frozenset({"-e", "-p", "--eval", "--print", "-"}),
    "deno": frozenset({"eval"}),
    "ruby": frozenset({"-e", "-"}),
    "perl": frozenset({"-e", "-E", "-"}),
    "php": frozenset({"-r", "-"}),
}


def is_carrier(head: str) -> bool:
    return head in CARRIER_HEADS or head.startswith("python")


_PACKAGE_WRAPPERS: Final = {"mvnw": "mvn", "mvnw.cmd": "mvn", "gradlew": "gradle", "gradlew.bat": "gradle"}


def package_rule_matches(head: str, program: str, rule: _Prefix, positionals: tuple[str, ...]) -> bool:
    if _PACKAGE_WRAPPERS.get(head, head) != program:
        return False
    if program == "mvn":
        return any(rule_matches(rule, (goal,)) for goal in positionals)
    if program == "gradle":
        tasks = (task.rsplit(":", 1)[-1] for task in positionals)
        return any(
            rule_matches(rule, (task,))
            or (rule == ("publish",) and task.startswith("publish") and task.endswith("Repository"))
            for task in tasks
        )
    return rule_matches(rule, positionals)


def rule_matches(rule: _Prefix, positionals: tuple[str, ...]) -> bool:
    if len(positionals) < len(rule):
        return False
    return all(
        word == expected if isinstance(expected, str) else word in expected
        for word, expected in zip(positionals, rule, strict=False)
    )
