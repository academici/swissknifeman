"""Run-report'ы Claude Code — общий stdlib-only примитив монорепо.

Поиск свежего run-report'а (<project>/.claude/runs/*.json) копировался в analyst
(digest) и maind (analyze) с расхождением: analyst раскрывал `~` в пути
(os.path.expanduser), maind — нет, и на `~`-пути молча возвращал None. Сведено сюда
с единой нормализацией пути. stdlib-only."""
import os
from pathlib import Path

from .io import safe_load_json


def find_run_report(project_path, session=None):
    """Разобранный свежий (или по session) run-report из <project>/.claude/runs/*.json.

    None если нет каталога/файла/битый JSON. Путь нормализуется через expanduser —
    `~/...` раскрывается (иначе отчёт молча «не находится»)."""
    runs = Path(os.path.expanduser(str(project_path))) / ".claude" / "runs"
    if not runs.is_dir():
        return None
    if session:
        f = runs / f"{session}.json"
        return safe_load_json(f, None) if f.is_file() else None
    files = [p for p in runs.glob("*.json") if p.is_file()]
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return safe_load_json(latest, None)
