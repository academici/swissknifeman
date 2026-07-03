#!/usr/bin/env python3
"""safe-dirs · вердикт для auto-approve — можно ли пропустить rm/rmdir мимо deny_hard.

Allowlist доверенных директорий — MACHINE-OWNED конфиг, лестница поиска:
  1. $SKM_SAFE_DIRS_CONFIG — явный override (эксклюзивный: задан → только он);
  2. <монорепо swissknifeman>/safe-dirs.json — ОСНОВНОЕ место (gitignored, шаблон
     safe-dirs.example.json рядом); корень репо резолвится через realpath лаунчера
     из PATH (swissknifeman/skiller/harness/maind — паттерн memory-хука);
  3. ~/.swissknifeman/safe-dirs.json — legacy-fallback (home оставлен памяти/реестру).
Плюс авто-включение путей проектов из ~/.swissknifeman/projects.json. Project-override
конфига хука (.claude/auto-approve.config.json) сюда НЕ влияет — враждебный репозиторий
не должен уметь разрешить себе rm вне своих папок.

Контракт: stdin — JSON события PreToolUse; stdout — строка "safe", если ВСЕ rm/rmdir
в команде валидированы против allowlist, иначе пусто. Любая ошибка/сомнение → пусто
(fail-closed: вызывающий lib/safedirs.sh без вердикта оставляет deny_hard как есть).

Дисциплина анализа (не эмулируем shell — отвергаем непонятое):
  · argv через shlex (кавычки честно), сегменты по операторам ; | & && || ( ) < >
  · rm/rmdir НЕ в голове сегмента (xargs rm, sudo rm, env-prefix) → unsafe;
    исключение — `git rm` (обратим, его маскирует сам analyze.sh)
  · флаги строго из белого списка; `--` учитывается; без аргументов → unsafe
  · пути: $ ` { } → unsafe; `..` как компонент → unsafe (лексически, до realpath);
    глоб → containment статического префикса; относительные — от cwd с cd-трекингом
  · containment по компонентам после realpath (symlink escape закрыт); корень
    safe-dir не удаляем (глоб по детям — можно); exclude; protect_git
Вердикт all-or-nothing на всю команду. Stdlib-only."""
import json
import os
import shlex
import shutil
import sys

_PUNCT = ";|&<>()"
_GLOB_CHARS = ("*", "?", "[")
_FORBIDDEN = ("$", "`", "{", "}")

_RM_LONG = {"--recursive", "--force", "--verbose", "--dir"}
_RM_SHORT = set("rRfvdiI")
_RMDIR_LONG = {"--verbose", "--ignore-fail-on-non-empty"}
_RMDIR_SHORT = set("v")


# ---------------------------------------------------------------- allowlist

def _repo_root():
    """Корень монорепо swissknifeman через realpath лаунчера из PATH (маркер —
    .claude-plugin/marketplace.json). Автономный мини-резолвер: хук живёт копией
    в ~/.claude/hooks без PYTHONPATH монорепо (осознанный дубль, как pack-guard)."""
    for name in ("swissknifeman", "skiller", "harness", "maind"):
        exe = shutil.which(name)
        if not exe:
            continue
        d = os.path.dirname(os.path.realpath(exe))
        for _ in range(6):
            if os.path.isfile(os.path.join(d, ".claude-plugin", "marketplace.json")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return None


def _config_path(home):
    """Лестница из докстринга модуля. env-override эксклюзивен (нет файла → off,
    без фолбэков) — детерминизм для тестов и ручного пина."""
    env = os.environ.get("SKM_SAFE_DIRS_CONFIG")
    if env:
        return env
    root = _repo_root()
    if root and os.path.isfile(os.path.join(root, "safe-dirs.json")):
        return os.path.join(root, "safe-dirs.json")
    return os.path.join(home, ".swissknifeman", "safe-dirs.json")


def load_allowlist(home, path=None):
    """roots/excludes (realpath) + cfg из safe-dirs.json (_config_path).
    Нет файла / битый JSON / version != 1 → None (фича выключена)."""
    try:
        with open(path or _config_path(home), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict) or cfg.get("version") != 1:
        return None
    dirs = [d for d in (cfg.get("dirs") or []) if isinstance(d, str)]
    if cfg.get("include_registered_projects", False):
        dirs += _registered_projects(home)
    home_real = os.path.realpath(home)
    roots = []
    for d in dirs:
        r = _norm_root(d, home, home_real)
        if r and r not in roots:
            roots.append(r)
    excludes = []
    for d in cfg.get("exclude") or []:
        if isinstance(d, str):
            e = _abs_real(d, home)
            if e and e not in excludes:
                excludes.append(e)
    return {"roots": roots, "excludes": excludes,
            "allow_globs": bool(cfg.get("allow_globs", True)),
            "protect_git": bool(cfg.get("protect_git", True))}


def _registered_projects(home):
    """projects[].path из реестра skiller; сбой реестра лишь сужает allowlist."""
    try:
        with open(os.path.join(home, ".swissknifeman", "projects.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        return [p["path"] for p in data.get("projects", [])
                if isinstance(p, dict) and isinstance(p.get("path"), str)]
    except (OSError, ValueError, AttributeError):
        return []


def _expand_tilde(path, home):
    """'~'/'~/x' → от переданного home (не от env); '~user' → None (не разрешаем)."""
    if path == "~":
        return home
    if path.startswith("~/"):
        return os.path.join(home, path[2:])
    if path.startswith("~"):
        return None
    return path


def _abs_real(path, home):
    """tilde-экспансия + realpath; относительный/неразрешимый путь → None."""
    p = _expand_tilde(path, home)
    if not p or not os.path.isabs(p):
        return None
    return os.path.realpath(p)


def _norm_root(path, home, home_real):
    """Корень allowlist. Не доверяем даже своему конфигу: '/', $HOME и предки
    $HOME игнорируются — safe-dir обязан быть УЖЕ дома или сбоку, не над ним."""
    r = _abs_real(path, home)
    if not r or r == os.sep:
        return None
    if r == home_real or home_real.startswith(r + os.sep):
        return None
    return r


# ---------------------------------------------------------------- разбор команды

def _tokenize(cmd):
    """Список сегментов [(sep_before, [tokens])]; None — shlex не смог (unsafe)."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=_PUNCT)
    lex.whitespace_split = True
    try:
        raw = list(lex)
    except ValueError:
        return None
    segs, cur, sep = [], [], ""
    for tok in raw:
        if tok and all(ch in _PUNCT for ch in tok):
            if cur:
                segs.append((sep, cur))
                cur = []
            sep = tok
        else:
            cur.append(tok)
    if cur:
        segs.append((sep, cur))
    return segs


def _is_branch_op(op):
    """Ветвление/фон/сабшелл — статически непредсказуемый cwd. Редиректы — нет."""
    if op in ("&&", ";") or all(ch in "<>" for ch in op):
        return False
    return True


def _cd_arg_resolvable(arg):
    """cd <literal>: только статически разрешимый аргумент ('cd -', глоб, $VAR,
    '..'-компоненты — нет: логический cd bash ≠ физический realpath)."""
    if arg.startswith("-"):
        return False
    if any(ch in arg for ch in _FORBIDDEN) or any(ch in arg for ch in _GLOB_CHARS):
        return False
    if ".." in arg.split("/"):
        return False
    return True


def _track_candidates(segs, cwd, home):
    """candidates-cwd ДО исполнения каждого сегмента (множество, т.к. `cd X; …`
    неоднозначен). Ветвление вместе с cd → ∅ всюду (v1, консервативно)."""
    base = {os.path.realpath(cwd)} if cwd else set()
    has_cd = any(t and t[0] in ("cd", "pushd", "popd") for _, t in segs)
    if has_cd and any(_is_branch_op(sep) for sep, _ in segs if sep):
        return [set()] * len(segs)
    result, cands = [], set(base)
    for i, (_, toks) in enumerate(segs):
        result.append(set(cands))
        head = toks[0] if toks else ""
        if head in ("pushd", "popd"):
            cands = set()
        elif head == "cd":
            args = toks[1:]
            if not args:
                new = {os.path.realpath(home)}
            elif len(args) == 1 and _cd_arg_resolvable(args[0]):
                a = _expand_tilde(args[0], home)
                if a is None:
                    new = set()
                elif os.path.isabs(a):
                    new = {os.path.realpath(a)}
                else:
                    new = {os.path.realpath(os.path.join(c, a)) for c in cands}
            else:
                new = set()
            if not new:
                cands = set()          # cd в неизвестное место → cwd неизвестен
            elif i + 1 < len(segs) and segs[i + 1][0] == "&&":
                cands = new            # после && rm исполнится только при успехе cd
            else:
                cands = cands | new    # `cd X; rm` — cd мог упасть, проверяем оба
    return result


# ---------------------------------------------------------------- пути

def _contained(p, allow, allow_root=False):
    """p (realpath) строго внутри одного из roots, вне exclude, вне .git."""
    root = next((r for r in allow["roots"]
                 if p == r or p.startswith(r + os.sep)), None)
    if root is None:
        return False
    if p == root and not allow_root:
        return False                   # сам корень safe-dir не удаляем
    for ex in allow["excludes"]:
        if p == ex or p.startswith(ex + os.sep):
            return False
    if allow["protect_git"] and ".git" in os.path.relpath(p, root).split(os.sep):
        return False                   # git — та самая страховка, её не сносим
    return True


def _path_safe(tok, candidates, allow, home):
    """Один операнд rm/rmdir. Fail-closed: непонятое → False."""
    if not tok or any(ch in tok for ch in _FORBIDDEN):
        return False
    if ".." in tok.split("/"):
        return False
    if tok.startswith("~"):
        if tok == "~" or not tok.startswith("~/"):
            return False               # '~' целиком / '~user' — не разрешаем
        tok = os.path.join(home, tok[2:])
    allow_root = False
    if any(ch in tok for ch in _GLOB_CHARS):
        if not allow["allow_globs"]:
            return False
        if allow["protect_git"] and not _glob_git_safe(tok):
            return False
        # containment по статическому dir-префиксу: раскрытие глоба даёт только
        # его детей ('..' отвергнут выше; rm по симлинку-матчу удалит линк, не цель)
        idx = min(tok.index(ch) for ch in _GLOB_CHARS if ch in tok)
        cut = tok.rfind("/", 0, idx)
        tok = tok[:cut + 1] if cut >= 0 else "."
        allow_root = True              # `root/*` удаляет детей, не корень — можно
    if os.path.isabs(tok):
        paths = [os.path.realpath(tok)]
    else:
        if not candidates:
            return False
        paths = [os.path.realpath(os.path.join(c, tok)) for c in candidates]
    return all(_contained(p, allow, allow_root) for p in paths)


def _glob_git_safe(pattern):
    """Глоб не должен уметь дотянуться до .git: bash-глоб матчит ведущую точку
    только литеральной '.', поэтому dot-компонент с метасимволами ('.git*', '.*')
    и литеральный '.git' в любом месте паттерна — отказ."""
    for comp in pattern.split("/"):
        if comp == ".git":
            return False
        if comp.startswith(".") and comp not in (".", "..") \
                and any(ch in comp for ch in _GLOB_CHARS):
            return False
    return True


# ---------------------------------------------------------------- сегменты

def _flag_ok(name, tok):
    if name == "rm":
        if tok.startswith("--"):
            return tok in _RM_LONG
        return len(tok) > 1 and all(ch in _RM_SHORT for ch in tok[1:])
    if tok.startswith("--"):
        return tok in _RMDIR_LONG      # -p/--parents лезет к предкам — отказ
    return len(tok) > 1 and all(ch in _RMDIR_SHORT for ch in tok[1:])


def _segment_safe(toks, candidates, allow, home):
    name, args, after_ddash = toks[0], [], False
    for tok in toks[1:]:
        if not after_ddash and tok == "--":
            after_ddash = True
        elif not after_ddash and tok.startswith("-") and tok != "-":
            if not _flag_ok(name, tok):
                return False
        else:
            args.append(tok)
    if not args:
        return False
    return all(_path_safe(a, candidates, allow, home) for a in args)


def command_is_safe(cmd, cwd, allow, home):
    """True ⇔ каждая rm/rmdir-команда в cmd валидирована против allowlist."""
    if not cmd or "\n" in cmd or "\r" in cmd:
        return False                   # многострочность → сегментация ненадёжна
    segs = _tokenize(cmd)
    if not segs:
        return False
    heads = []
    for _, toks in segs:
        for j, t in enumerate(toks):
            if t in ("rm", "rmdir") and j > 0:
                if toks[0] == "git" and j == 1:
                    continue           # git rm обслуживает маскирование analyze.sh
                return False           # xargs rm / sudo rm / FOO=x rm / rm как арг
        if toks and toks[0] in ("rm", "rmdir"):
            heads.append(True)
    if not heads:
        return False                   # нечего разрешать — не маскируем
    cands = _track_candidates(segs, cwd, home)
    return all(_segment_safe(toks, cands[i], allow, home)
               for i, (_, toks) in enumerate(segs)
               if toks and toks[0] in ("rm", "rmdir"))


def main():
    try:
        event = json.load(sys.stdin)
        cmd = (event.get("tool_input") or {}).get("command") or ""
        cwd = event.get("cwd") or ""
        home = os.path.expanduser("~")
        allow = load_allowlist(home)
        if allow and command_is_safe(cmd, cwd, allow, home):
            print("safe")
    except Exception:
        pass  # fail-closed: вердикта нет — deny_hard остаётся в силе


if __name__ == "__main__":
    main()
