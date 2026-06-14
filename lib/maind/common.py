"""Общие утилиты maind: окружение (Env), вывод, парсинг аргументов, atomic JSON, HTTP.

Стиль и инварианты — как в swissknifeman/brain: окружение передаётся явно через
Env (без модульных глобалей), JSON-хранилища пишутся атомарно, сетевые вызовы —
на stdlib urllib (никаких сторонних зависимостей в рантайме)."""
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

HOME = Path.home()
DB_VERSION = 1
SLUG_RE = re.compile(r"[^a-z0-9-]")


@dataclass(frozen=True)
class Env:
    """Контекст запуска: корень репозитория maind, текущая команда, домашний каталог.

    Значения передаются явно (не модульные глобали) — функции тестируемы: можно
    подсунуть временный root и home, не трогая argv процесса. frozen=True: контекст
    запуска неизменен; __post_init__ нормализует root/home в Path (принимаем str/Path)."""

    root: Path
    cmd: str = ""
    home: Path = field(default_factory=lambda: HOME)

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root))
        object.__setattr__(self, "home", Path(self.home))

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
        return self.root / "config" / "memory" / "iii-config.yaml"

    @property
    def default_config(self):
        return self.root / ".maind.json"

    @property
    def example_config(self):
        return self.root / ".maind.example.json"

    @property
    def env_file(self):
        return self.root / ".env"


# ── вывод и завершение ─────────────────────────────────────────────────────
def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"WARN: {msg}", file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def confirm(prompt):
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def sanitize(name):
    """Slug: lower, пробелы/подчёркивания → дефис, прочее убрать, схлопнуть дефисы."""
    name = name.lower().replace(" ", "-").replace("_", "-")
    name = SLUG_RE.sub("", name)
    return re.sub(r"-{2,}", "-", name).strip("-")


# ── парсинг аргументов (флаги + позиционные, стиль brain) ───────────────────
def parse_args(args, spec, max_pos=0):
    """spec: {'--flag': 'str'|'bool'}; возвращает (opts, positionals).

    opts ключуются по имени флага без '--', с '-'→'_'. -h/--help → opts['help'].
    Неизвестный флаг, нехватка значения или перебор позиционных → die."""
    opts = {k.lstrip("-").replace("-", "_"): ("" if t == "str" else False)
            for k, t in spec.items()}
    opts.setdefault("help", False)
    pos = []
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


# ── JSON-хранилища (atomic write + устойчивое чтение) ───────────────────────
def atomic_write_json(path, data, *, version=None):
    """Пишет JSON атомарно (tmp + os.replace) c финальным '\\n'. Если version задан
    и data — dict, проставляет data['version']=version первым ключом."""
    path = Path(path)
    if version is not None and isinstance(data, dict):
        rest = {k: v for k, v in data.items() if k != "version"}
        data = {"version": version, **rest}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


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
