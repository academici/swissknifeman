"""Общие утилиты harness: окружение (Env), парсинг flag'ов.

Дословно общий с skiller/maind/brain код (die/warn/now_iso/confirm/sanitize +
ядро Env, atomic JSON) вынесен в общий core; здесь — специфика harness
(path-property пакета, parse_flags)."""
from dataclasses import dataclass

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_text, confirm, die, find_monorepo_root,
    now_iso, parse_flags, run_cmd, safe_load_json, sanitize, warn,
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
    def agent_packs_dir(self):
        """Каталог паков субагентов: agent-packs/<pack>/pack.json."""
        return self.configs_dir / "agent-packs"

    @property
    def apply_script(self):
        return self.root / "scripts" / "apply-permissions.sh"


# parse_flags — из общего core (реэкспорт выше); раньше дублировался здесь.
