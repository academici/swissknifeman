"""Shared CLI parsing and safe subprocess execution primitives. stdlib-only."""
import subprocess
from pathlib import Path

from .term import die


def parse_flags(args: list[str], spec: dict[str, str]) -> dict[str, object]:
    """spec: {'--flag': 'str'|'bool'}; returns dict keyed by flag name sans --.

    Any argument outside ``spec`` fails; ``-h``/``--help`` sets ``out['help']``."""
    out: dict[str, object] = {
        k.lstrip("-").replace("-", "_"): ("" if t == "str" else False)
        for k, t in spec.items()
    }
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            out["help"] = True
            i += 1
            continue
        if a not in spec:
            die(f"неизвестный флаг: {a}")
        key = a.lstrip("-").replace("-", "_")
        if spec[a] == "bool":
            out[key] = True
            i += 1
        else:
            if i + 1 >= len(args):
                die(f"флаг {a} требует значение")
            out[key] = args[i + 1]
            i += 2
    out.setdefault("help", False)
    return out


def parse_args(args: list[str], spec: dict[str, str],
               max_pos: int = 0) -> tuple[dict[str, object], list[str]]:
    """Parse flags and positional arguments, returning ``(options, positionals)``.

    Unknown flags, missing values, and excess positionals fail.
    """
    opts: dict[str, object] = {
        k.lstrip("-").replace("-", "_"): ("" if t == "str" else False)
        for k, t in spec.items()
    }
    opts.setdefault("help", False)
    pos: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            opts["help"] = True
            i += 1
            continue
        if a.startswith("-") and a != "-":
            if a not in spec:
                die(f"неизвестный флаг: {a}")
            key = a.lstrip("-").replace("-", "_")
            if spec[a] == "bool":
                opts[key] = True
                i += 1
            else:
                if i + 1 >= len(args):
                    die(f"флаг {a} требует значение")
                opts[key] = args[i + 1]
                i += 2
        else:
            pos.append(a)
            i += 1
    if len(pos) > max_pos:
        die(f"лишние аргументы: {' '.join(pos[max_pos:])}")
    return opts, pos


def run_cmd(argv: list[str], *, cwd: "str | Path | None" = None,
            capture: bool = False, text: bool = True,
            timeout: "float | None" = None,
            check: bool = True) -> subprocess.CompletedProcess:
    """Run an argv-only subprocess, never ``shell=True``.

    Missing commands, timeouts, and checked nonzero exits call ``die``.
    """
    try:
        result = subprocess.run(
            argv, cwd=str(cwd) if cwd is not None else None,
            capture_output=capture, text=text, timeout=timeout, check=False,
        )
    except FileNotFoundError:
        die(f"команда не найдена: {argv[0]}")
    except subprocess.TimeoutExpired:
        die(f"команда не уложилась в {timeout}s: {' '.join(argv)}")
    except OSError as e:
        die(f"ошибка запуска {argv[0]}: {e}")
    if check and result.returncode != 0:
        tail = ""
        if capture and result.stderr:
            tail = f"\n{result.stderr.strip()}"
        die(f"команда завершилась с кодом {result.returncode}: "
            f"{' '.join(argv)}{tail}")
    return result
