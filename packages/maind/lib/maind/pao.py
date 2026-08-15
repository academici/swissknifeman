"""Laravel PAO onboarding invariant for compact PHP tool output.

For PHP/Laravel projects on PHP 8.3+, `laravel/pao` must be installed or the
project must record an opt-out. Composer is invoked only through subprocess;
dependency changes require interactive approval.
"""
import re
import subprocess

from .common import warn

PHP_TYPES = {"laravel-project", "php-package"}
MIN_PHP = (8, 3)


def applies(project):
    return project.get("type") in PHP_TYPES


def _php_version(path):
    """Return (major, minor) from `php -v`, or None when unavailable/unparseable."""
    try:
        out = subprocess.run(["php", "-v"], cwd=str(path), capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"PHP (\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _installed(path):
    lock = path / "composer.lock"
    if lock.is_file() and "laravel/pao" in lock.read_text(encoding="utf-8", errors="ignore"):
        return True
    return (path / "vendor" / "laravel" / "pao").is_dir()


def status(project, path):
    """Return PAO status from filesystem facts and `php -v` without blind execution."""
    if not applies(project):
        return "n-a"
    if project.get("pao_opt_out"):
        return "opt-out"
    ver = _php_version(path)
    if not ver or ver < MIN_PHP:
        return "php-too-old"
    return "installed" if _installed(path) else "missing"


_SKIP_DETAIL = {"n-a": "не PHP-проект", "opt-out": "opt-out зафиксирован (pao_opt_out)",
                "php-too-old": "PHP < 8.3 — PAO не поддерживается"}


def apply_pao(project, path, *, interactive, dry):
    """Provision PAO interactively; noninteractive mode warns without installing."""
    pid = project.get("id", "?")
    st = status(project, path)
    if st in _SKIP_DETAIL:
        return {"name": "pao", "status": "skipped", "detail": _SKIP_DETAIL[st]}
    if st == "installed":
        return {"name": "pao", "status": "ok", "detail": "laravel/pao уже установлен"}
    # st == "missing"
    if dry:
        return {"name": "pao", "status": "skipped", "detail": "--dry-run"}
    if not interactive:
        warn(f"[{pid}] laravel/pao не установлен — вывод PHP-тестов/анализа агенту "
            "останется многословным (тысячи токенов вместо ~20). Поставь вручную: "
            "composer require laravel/pao --dev (либо зафиксируй осознанный opt-out — "
            "поле проекта pao_opt_out=true в config.json)")
        return {"name": "pao", "status": "skipped", "detail": "не в интерактиве — см. warn"}
    ans = input(f"[{pid}] Установить laravel/pao --dev (токен-экономия вывода PHP-тестов/"
               "анализа для агента)? [Y]/n: ").strip().lower()
    if ans in ("n", "no", "нет"):
        warn(f"[{pid}] laravel/pao пропущен по выбору — поставь вручную позже: "
            "composer require laravel/pao --dev")
        return {"name": "pao", "status": "skipped", "detail": "отклонено пользователем"}
    try:
        r = subprocess.run(["composer", "require", "laravel/pao", "--dev"],
                           cwd=str(path), capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        warn(f"[{pid}] composer require laravel/pao упал: {e}")
        return {"name": "pao", "status": "failed", "detail": str(e)}
    if r.returncode != 0:
        warn(f"[{pid}] composer require laravel/pao --dev rc={r.returncode}: "
            f"{(r.stderr or '').strip()[:200]}")
        return {"name": "pao", "status": "failed",
                "detail": f"composer require rc={r.returncode}"}
    return {"name": "pao", "status": "ok", "detail": "composer require laravel/pao --dev"}
