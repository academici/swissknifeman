"""release — сборка предложения релиза монорепо (2026.07.10-SKM-ROADMAP-005 P5.3, опциональная механизация).

Читает `[Unreleased]` корневого `CHANGELOG.md`, классифицирует semver-bump из
conventional commits со времени последнего umbrella-тега (`vX.Y.Z`) и —
БЕЗ `--dry-run` — переносит секцию в `[X.Y.Z] - <дата>` + печатает готовую
команду тега. НИКОГДА не тегает/не пушит сам (D34) и НЕ выводит MAJOR: признак
breaking-изменения — отказ, версия остаётся ручным решением владельца.

Semver-oracle (minor=capability/feat, patch=fix/perf) — из
`plans/SKM-AUDIT-004/findings/P5-release.md`, НЕ переизобретён здесь.
stdlib-only, `Env` передаётся явно (тестируемо в tmpdir)."""
import re
import sys
from datetime import date

from core import atomic_write_text, backup_file, find_monorepo_root, run_cmd

from .common import parse_flags

# Типы conventional-commit, дающие semver-сигнал; `!` после типа/скоупа либо
# `BREAKING CHANGE` в теле коммита — маркер breaking (см. classify_bump).
CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|perf|refactor|docs|chore|test|style|ci|build)"
    r"(?:\([^)]*\))?(?P<bang>!)?:\s*")
MINOR_TYPES = {"feat"}
PATCH_TYPES = {"fix", "perf"}
BREAKING_MARKER = "BREAKING CHANGE"
TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
UNRELEASED_RE = re.compile(r"^##\s*\[Unreleased\]\s*$", re.IGNORECASE)
NEXT_HEADING_RE = re.compile(r"^##\s*\[")


def _last_tag(root):
    """Последний umbrella-тег `vX.Y.Z` (`git describe --tags --abbrev=0`).
    None — тегов нет (первый релиз) либо `root` не git-репозиторий."""
    result = run_cmd(["git", "describe", "--tags", "--match", "v[0-9]*", "--abbrev=0"],
                      cwd=root, capture=True, check=False)
    if result.returncode != 0:
        return None
    tag = result.stdout.strip()
    return tag or None


def _commits_since(root, tag):
    """[(subject, body), ...] коммитов в диапазоне `tag..HEAD` (весь лог, если
    tag=None). Разделители `\\x1e`/`\\x1f` — практически не встречаются в тексте
    коммита, безопаснее построчного разбора `git log --oneline`."""
    range_arg = f"{tag}..HEAD" if tag else "HEAD"
    result = run_cmd(["git", "log", range_arg, "--pretty=format:%s%x1f%b%x1e"],
                      cwd=root, capture=True, check=False)
    if result.returncode != 0 or not result.stdout:
        return []
    out = []
    for chunk in result.stdout.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        subject, _, body = chunk.partition("\x1f")
        out.append((subject.strip(), body.strip()))
    return out


def classify_bump(commits):
    """(bump, reason) из `[(subject, body), ...]`.

    bump: 'breaking' (отказ — D34, MAJOR НЕ выводим, reason=подозрительный subject) ·
    'minor' (есть feat:) · 'patch' (только fix:/perf:) · None (нечего релизить,
    в диапазоне нет conventional-коммитов с сигналом). breaking проверяется ПЕРВЫМ
    и коротким замыканием — не гадаем версию при малейшем подозрении на breaking."""
    minor = patch = False
    for subject, body in commits:
        m = CONVENTIONAL_RE.match(subject)
        if not m:
            continue
        if m.group("bang") or BREAKING_MARKER in body:
            return "breaking", subject
        t = m.group("type")
        if t in MINOR_TYPES:
            minor = True
        elif t in PATCH_TYPES:
            patch = True
    if minor:
        return "minor", None
    if patch:
        return "patch", None
    return None, None


def bump_version(tag, bump):
    """Новый `vX.Y.Z` из предыдущего тега + bump ('minor'|'patch'). Без тега —
    первый релиз (`v0.1.0`/`v0.0.1`). tag не матчит `vX.Y.Z` → None (вызывающий
    отказывается вместо угадывания)."""
    if tag is None:
        return "v0.1.0" if bump == "minor" else "v0.0.1"
    m = TAG_RE.match(tag)
    if not m:
        return None
    major, minor_v, patch_v = (int(x) for x in m.groups())
    if bump == "minor":
        return f"v{major}.{minor_v + 1}.0"
    return f"v{major}.{minor_v}.{patch_v + 1}"


def read_unreleased_section(text):
    """(lines, start, end, body) секции `## [Unreleased]` текста CHANGELOG.
    `body` — строки между заголовком и следующим `## [...]` (или концом файла),
    БЕЗ самого заголовка. None — секции в файле нет."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if UNRELEASED_RE.match(ln):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if NEXT_HEADING_RE.match(lines[j]):
            end = j
            break
    return lines, start, end, lines[start + 1:end]


def unreleased_is_empty(body_lines):
    """Пусто = ни одной непустой строки, не считая `###`-подзаголовков групп
    Keep a Changelog (`### Added` без записей — тоже «пусто»)."""
    return not any(ln.strip() and not ln.strip().startswith("###") for ln in body_lines)


def _release_changelog(text, new_version):
    """Текст CHANGELOG после переноса `[Unreleased]` → `[new_version] - <дата>`:
    старая секция освобождается (пустая `## [Unreleased]`), её содержимое едет под
    новый заголовок версии. Не трогает остальные секции файла."""
    lines, start, end, body = read_unreleased_section(text)
    new_heading = f"## [{new_version.removeprefix('v')}] - {date.today().isoformat()}"
    new_lines = (lines[:start] + ["## [Unreleased]", "", new_heading]
                 + body + lines[end:])
    return "\n".join(new_lines) + "\n"


def cmd_release(env, argv):
    opts = parse_flags(argv, {"--dry-run": "bool"})
    if opts["help"]:
        print("skiller release [--dry-run]\n"
              "  Собирает предложение релиза монорепо: semver-bump из conventional "
              "commits со времени последнего тега (feat:->minor, fix:/perf:->patch) "
              "+ перенос [Unreleased] -> [X.Y.Z] в CHANGELOG.md + печать команды тега.\n"
              "  MAJOR никогда не выводится — breaking-маркер даёт отказ, версия "
              "остаётся решением владельца. git tag/push НЕ исполняются.\n"
              "  --dry-run: только печать плана, CHANGELOG.md не меняется.")
        return

    root = find_monorepo_root(env.root) or env.root
    changelog = root / "CHANGELOG.md"
    if not changelog.is_file():
        print(f"skiller release: {changelog} не найден — нечего собирать.")
        return

    tag = _last_tag(root)
    commits = _commits_since(root, tag)
    bump, reason = classify_bump(commits)

    if bump == "breaking":
        print(f"skiller release: подозрение на breaking-изменение (коммит: {reason!r}) "
              "— MAJOR-версия ВСЕГДА ручное решение владельца, автоматика её не "
              "выводит. Оцените диапазон сами и проставьте версию вручную.")
        sys.exit(1)

    if bump is None:
        print(f"skiller release: со времени {tag or '(первого коммита)'} нет "
              "conventional-коммитов feat/fix/perf — нечего релизить.")
        return

    new_version = bump_version(tag, bump)
    if new_version is None:
        print(f"skiller release: последний тег {tag!r} не матчит vX.Y.Z — "
              "проставьте версию вручную.")
        sys.exit(1)

    try:
        text = changelog.read_text(encoding="utf-8")
    except OSError as e:
        print(f"skiller release: {changelog} недоступен для чтения ({e}) — пропуск.")
        return

    parsed = read_unreleased_section(text)
    if parsed is None:
        print(f"skiller release: секция `## [Unreleased]` не найдена в {changelog} "
              "— переносить нечего.")
        return
    if unreleased_is_empty(parsed[3]):
        print("skiller release: секция `[Unreleased]` пуста — переносить нечего "
              "(заполните CHANGELOG перед релизом, см. `oss-dev/release-engineering`).")
        return

    if (root / ".agents/plugins/marketplace.json").is_file():
        from .release_attestation import build, check_transition
        errors = check_transition(build(root, ref=tag), build(root)) if tag else []
        if errors:
            print("skiller release: " + "; ".join(errors), file=sys.stderr)
            sys.exit(1)

    print(f"skiller release: предложение — {tag or '(нет тега)'} -> {new_version} "
          f"({bump}, {len(commits)} коммит(ов) в диапазоне)")
    tag_cmd = f'git tag -a {new_version} -m "release: {new_version}"'

    if opts["dry_run"]:
        print(f"[dry-run] CHANGELOG.md не изменён. После проверки: {tag_cmd}")
        return

    backup_file(changelog)
    atomic_write_text(changelog, _release_changelog(text, new_version))
    if (root / ".agents/plugins/marketplace.json").is_file():
        from .release_attestation import cmd_attest
        args = ["--release", new_version]
        if tag:
            args += ["--previous", tag]
        cmd_attest(env, args)
    print(f"CHANGELOG.md обновлён: [Unreleased] -> [{new_version.removeprefix('v')}]. "
          f"Тег и push — вручную:\n  {tag_cmd}\n  git push origin {new_version}")
