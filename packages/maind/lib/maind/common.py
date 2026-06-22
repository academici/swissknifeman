"""Общие утилиты maind: окружение (Env), парсинг аргументов, atomic JSON, HTTP.

Дословно общий с swissknifeman/brain код (die/warn/now_iso/confirm/sanitize +
ядро Env) вынесен в общий core; здесь — специфика maind (path-property узла,
parse_args с позиционными, atomic JSON, managed-block, HTTP на stdlib urllib)."""
import copy
import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые исторически берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, confirm, die,
    find_monorepo_root, now_iso, parse_args, run_cmd, safe_load_json,
    sanitize, warn,
)

DB_VERSION = 1


@dataclass(frozen=True)
class Env(BaseEnv):
    """Контекст запуска maind: ядро (root/cmd/home) — из BaseEnv; здесь только
    path-property узла (~/.maind, root/data, config)."""

    # ── состояние пользователя (~/.maind) ──────────────────────────────────
    @property
    def state_dir(self):
        return self.home / ".maind"

    @property
    def projects_db(self):
        return self.state_dir / "projects.json"

    @property
    def agents_db(self):
        return self.state_dir / "agents.json"

    # ── runtime-данные узла (root/data, gitignored) ────────────────────────
    @property
    def data_dir(self):
        return self.root / "data"

    @property
    def graph_db(self):
        return self.data_dir / "graph.db"

    @property
    def memory_pidfile(self):
        return self.data_dir / "agentmemory.pid"

    @property
    def memory_log(self):
        return self.data_dir / "agentmemory.log"

    # ── конфигурация узла ──────────────────────────────────────────────────
    @property
    def memory_config(self):
        """Конфиг agent-memory демона. Env `MAIND_III_CONFIG` переопределяет путь
        (по образцу `MAIND_SKM_BIN`/`MAIND_BRAIN_BIN` в orchestrate); иначе —
        `config/memory/iii-config.yaml` в пакете."""
        override = os.environ.get("MAIND_III_CONFIG")
        if override:
            return Path(os.path.expanduser(override))
        return self.root / "config" / "memory" / "iii-config.yaml"

    @property
    def monorepo_root(self):
        """Корень монорепо — каталог с `packages/`/`core/` выше пакета. Конфиг узла
        (`config.json`) общий и лежит здесь. Fallback: сам root (standalone)."""
        return find_monorepo_root(self.root) or self.root

    @property
    def default_config(self):
        """Конфиг узла. Канонически — `config.json` в корне монорепо. Обратная
        совместимость: если его нет, но есть старый `.maind.json` (в корне или в
        пакете) — берём его (миграция без поломки существующих установок)."""
        root_cfg = self.monorepo_root / "config.json"
        if root_cfg.exists():
            return root_cfg
        for legacy in (self.monorepo_root / ".maind.json", self.root / ".maind.json"):
            if legacy.exists():
                return legacy
        return root_cfg  # путь по умолчанию для записи/подсказок — новый

    @property
    def example_config(self):
        """Шаблон конфига — `config.example.json` в корне монорепо (с legacy-fallback)."""
        root_ex = self.monorepo_root / "config.example.json"
        if root_ex.exists():
            return root_ex
        legacy = self.monorepo_root / ".maind.example.json"
        return legacy if legacy.exists() else root_ex

    @property
    def env_file(self):
        return self.root / ".env"


# die/warn/now_iso/confirm/sanitize — из общего core (реэкспорт выше).


# parse_args — из общего core (реэкспорт выше); раньше дублировался здесь
# (надмножество parse_flags с позиционными, стиль brain).


# ── файловые помощники ──────────────────────────────────────────────────────
def backup_file(path):
    """Копия <path>.bak, если файл существует. Возвращает путь бэкапа или None."""
    path = Path(path)
    if not path.exists():
        return None
    bak = path.with_name(path.name + ".bak")
    shutil.copy2(path, bak)
    return bak


# ── управляемый markdown-блок (идемпотентная вставка/обновление) ────────────
def content_hash(text):
    """Короткий стабильный хэш содержимого (для детекта дрейфа управляемых артефактов)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def managed_block(content, marker):
    """Управляемый блок с маркерами begin/end и хэшем: maind — единственный его писатель."""
    h = content_hash(content)
    return (f"<!-- {marker} hash={h} (managed by maind — не редактировать вручную) -->\n"
            f"{content.rstrip()}\n<!-- /{marker} -->")


def upsert_block(text, content, marker):
    """Вставить/обновить управляемый блок в text. Возвращает (new_text, changed, state),
    state ∈ {absent→install, stale→update, fresh→skip}. Существующий блок ищется по маркерам,
    чужой текст не трогается; отсутствует — добавляется в конец."""
    block = managed_block(content, marker)
    pat = re.compile(rf"<!-- {re.escape(marker)}\b.*?<!-- /{re.escape(marker)} -->",
                     re.DOTALL)
    m = pat.search(text or "")
    if m is None:
        sep = "" if not text or text.endswith("\n") else "\n"
        joiner = "\n" if text else ""
        return (text or "") + sep + joiner + block + "\n", True, "absent"
    if m.group(0).strip() == block.strip():
        return text, False, "fresh"
    return text[:m.start()] + block + text[m.end():], True, "stale"


# ── JSON-хранилища (atomic write — из core; устойчивое чтение — здесь) ───────
def load_json_db(path, default):
    """Читает JSON-БД. Битый файл → бэкап .corrupt.<date> + warn + копия default.
    Версия новее DB_VERSION → die. default не мутируется (возвращается deepcopy)."""
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        db = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_name(f"{path.name}.corrupt.{date.today().isoformat()}")
        path.rename(backup)
        warn(f"{path} повреждён — переименован в {backup.name}, начинаю заново")
        return copy.deepcopy(default)
    if isinstance(db, dict) and db.get("version", 1) > DB_VERSION:
        die(f"{path} записан более новой версией maind — обновите репозиторий (git pull)")
    return db


# ── HTTP (stdlib urllib) ────────────────────────────────────────────────────
def http_get_json(url, *, timeout=5):
    """GET → распарсенный JSON. Сетевые ошибки → RuntimeError с понятным текстом."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} от {url}") from e
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"нет связи с {url}: {getattr(e, 'reason', e)}") from e


def http_post_json(url, payload, *, timeout=10):
    """POST JSON → распарсенный JSON-ответ (пустой ответ → {})."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} от {url}") from e
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"нет связи с {url}: {getattr(e, 'reason', e)}") from e


def ping(url, *, timeout=3):
    """True, если по url вообще отвечает HTTP (даже 4xx). HTTPError = сервис жив
    (как в brain healthcheck); URLError/OSError = недоступен."""
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False
