"""Pure checkout hygiene checks from read-only host observations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import TYPE_CHECKING

from skm.modules.integrations.domain.hook_rules import safe_shell_words
from skm.modules.integrations.domain.presets import dart_package_name
from skm.modules.integrations.domain.target import TargetId

from .claude import hook_commands
from .context import finding, mapping, strings

if TYPE_CHECKING:
    from skm.modules.integrations.domain.reports import CheckResult

    from .context import DoctorContext

__all__ = ["CHECKS", "script_path"]

_WORD_PROBLEM = re.compile(
    r"(?<![\w/-])(?:pest\s*/\s*phpunit|npm\s*/\s*(?:pnpm|yarn)|pip\s*/\s*uv)(?![\w/-])", re.I
)
_FORMATTERS = (
    re.compile(r"(?:^|[;&|]\s*)\s*(?:[\w./-]+/)?pint\b(?![^;&|]*\s--test\b)"),
    re.compile(r"(?:^|[;&|]\s*)\s*(?:[\w./-]+/)?dart\s+format\b(?![^;&|]*\s--output(?:=|\s+)none\b)"),
    re.compile(
        r"(?:^|[;&|]\s*)\s*(?:(?:npx|pnpm exec|yarn)\s+)?(?:[\w./-]+/)?prettier\b[^;&|]*\s(?:--write|-w)\b"
    ),
    re.compile(
        r"(?:^|[;&|]\s*)\s*(?:uv run\s+)?(?:[\w./-]+/)?ruff\s+format\b(?![^;&|]*\s--(?:check|diff)\b)"
    ),
)
_INTERPRETERS = frozenset({"bash", "sh", "zsh", "fish", "python", "python3", "ruby", "node", "php"})
_SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".py", ".rb", ".js", ".mjs", ".php")


def script_path(argv: Sequence[str]) -> str | None:
    if not argv:
        return None
    command = argv[0].rsplit("/", 1)[-1]
    if command in _INTERPRETERS:
        for operand in argv[1:]:
            if operand in {"-c", "-e", "-l", "--eval", "-m", "--command", "-"}:
                return None
            if not operand.startswith("-"):
                return operand
        return None
    if argv[0].endswith(_SCRIPT_SUFFIXES) or argv[0].startswith(("./", "/", "~/")):
        return argv[0]
    return None


def agents_size(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    text = ctx.hygiene.files.get("AGENTS.md", "")
    size, lines = len(text.encode()), len(text.splitlines())
    if size > 32 * 1024:
        return finding(
            ctx,
            "hygiene.agents_md_size",
            "error",
            "AGENTS.md size",
            [
                ("AGENTS.md", f"{size} bytes exceeds the 32 KiB limit"),
            ],
        )
    return finding(
        ctx,
        "hygiene.agents_md_size",
        "warning",
        "AGENTS.md size",
        ([("AGENTS.md", f"{lines} lines exceeds the 200-line guideline")] if lines > 200 else []),
    )


def ambiguous_commands(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "hygiene.slash_ambiguity",
        "warning",
        "Ambiguous command alternatives",
        (
            (path, f"Line {number} gives multiple commands with a slash")
            for path in ("AGENTS.md", "CLAUDE.md")
            for number, line in enumerate(ctx.hygiene.files.get(path, "").splitlines(), 1)
            if _WORD_PROBLEM.search(line)
        ),
    )


def hidden_unicode(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str, str]] = []
    for path, content in ctx.hygiene.files.items():
        hidden = sorted(
            {
                f"U+{ord(char):04X}"
                for char in content
                if unicodedata.category(char) == "Cf"
                or char in {"\u034f", "\u115f", "\u1160", "\u2800", "\u3164", "\uffa0"}
            }
        )
        if hidden:
            problems.append((path, "Hidden Unicode characters " + ", ".join(hidden)))
    return finding(ctx, "hygiene.hidden_unicode", "error", "Hidden Unicode", problems)


def post_tool_formatter(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    commands: list[tuple[str, str]] = []
    for layer in ctx.layers:
        hooks = mapping(mapping(layer.get("data")).get("hooks"))
        for event in ("PostToolUse", "AfterTool", "postToolUse"):
            commands.extend((str(layer.get("path")), command) for command in hook_commands(hooks.get(event)))
    for sub in ctx.subscription_facts:
        if sub.get("enabled") is not True or "client:post_tool" not in strings(sub.get("event_types")):
            continue
        target = mapping(sub.get("target"))
        argv = strings(target.get("argv"))
        if argv:
            commands.append((f"hooks.subscriptions.{sub['id']}", " ".join(argv)))
    return finding(
        ctx,
        "hygiene.post_tool_mutating_formatter",
        "warning",
        "Post-tool formatters",
        (
            (path, "A post-tool hook runs a mutating formatter; run it on Stop")
            for path, command in dict.fromkeys(commands)
            if any(pattern.search(command) for pattern in _FORMATTERS)
        ),
    )


def script_trust_and_exec(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str, str]] = []
    for script in ctx.hygiene.scripts:
        if not script.checkout_file:
            problems.append((script.path, "Hook script cannot be read as a checkout file"))
        elif not script.executable:
            problems.append((script.path, "Hook script is missing execute permission"))
        if not script.trusted:
            detail = (
                f"Hook subscription {script.subscription_id} has no matching trusted command digest"
                if script.subscription_id is not None
                else "Native hook script has no SKM subscription trust"
            )
            problems.append((script.path, detail))
    return finding(
        ctx, "hygiene.hook_script_trust_and_exec", "error", "Hook script permissions and trust", problems
    )


def _matches_tool(matcher: object, tool: str) -> bool:
    if matcher is None or matcher == "" or matcher == "*":
        return True
    if not isinstance(matcher, str):
        return False
    try:
        return re.search(matcher, tool) is not None
    except re.error:
        return False


def laravel_db_guard(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    composer = ctx.hygiene.files.get("composer.json", "")
    testcase = ctx.hygiene.files.get("tests/TestCase.php", "")
    laravel = '"laravel/framework"' in composer or (
        r"Illuminate\Foundation\Testing" in testcase and "phpunit.xml" in ctx.hygiene.files
    )
    event, tool = (
        ("BeforeTool", "run_shell_command") if ctx.target is TargetId.GEMINI_CLI else ("PreToolUse", "Bash")
    )
    settings = ctx.effective
    groups = mapping(settings.get("hooks")).get(event)
    commands = (
        command
        for group in (groups if isinstance(groups, list) else ())
        if _matches_tool(mapping(group).get("matcher"), tool)
        for command in hook_commands(mapping(group).get("hooks"))
    )
    guarded = False
    for command in commands:
        try:
            words = safe_shell_words(command)
        except ValueError:
            continue
        guarded |= (
            words[0].rsplit("/", 1)[-1] == "skm-hook"
            and "--surface" in words
            and words[words.index("--surface") + 1 : words.index("--surface") + 2] == ("security.safe_dirs",)
        )
    return finding(
        ctx,
        "hygiene.laravel_db_guard",
        "warning",
        "Laravel database guard",
        (
            [("composer.json", "Laravel checkout has no active SAFE_DIRS database guard")]
            if laravel and (not guarded or settings.get("disableAllHooks") is True)
            else []
        ),
    )


def dart_skill_prefix(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    package = dart_package_name(ctx.hygiene.files.get("pubspec.yaml"))
    return finding(
        ctx,
        "hygiene.dart_package_skill_prefix",
        "warning",
        "Dart package skill prefix",
        (
            (path, f"Consumer skill directory must begin with {package}-")
            for path in ctx.hygiene.skills
            if package is not None and not path.split("/")[1].startswith(package + "-")
        ),
    )


CHECKS = (
    agents_size,
    ambiguous_commands,
    hidden_unicode,
    post_tool_formatter,
    script_trust_and_exec,
    laravel_db_guard,
    dart_skill_prefix,
)
