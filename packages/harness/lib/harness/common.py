"""Общие утилиты harness: окружение (Env), парсинг flag'ов.

Дословно общий с skiller/maind/brain код (die/warn/now_iso/confirm/sanitize +
ядро Env, atomic JSON) вынесен в общий core; здесь — специфика harness
(path-property пакета, parse_flags)."""
from dataclasses import dataclass

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_text, confirm, die, find_monorepo_root,
    now_iso, sanitize, warn,
)


@dataclass(frozen=True)
class Env(BaseEnv):
    """Контекст запуска harness: ядро (root/cmd/home) — из BaseEnv; здесь только
    path-property пакета (configs/claude-code, scripts/apply-permissions.sh).
    Пакет stateless — собственного state-каталога (~/.harness) нет."""

    @property
    def configs_dir(self):
        """Каталог пресетов харнеса: settings.*.json, mcp/, hooks/."""
        return self.root / "configs" / "claude-code"

    @property
    def mcp_dir(self):
        return self.configs_dir / "mcp"

    @property
    def apply_script(self):
        return self.root / "scripts" / "apply-permissions.sh"


# --- flag parsing -------------------------------------------------------------
def parse_flags(args, spec):
    """spec: {'--flag': 'str'|'bool'}; returns dict keyed by flag name sans --."""
    out = {k.lstrip("-").replace("-", "_"): ("" if t == "str" else False)
           for k, t in spec.items()}
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
