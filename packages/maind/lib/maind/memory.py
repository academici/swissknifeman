"""Память узла: жизненный цикл agent-memory демона + HTTP-обёртка со scope'ами.

agent-memory — внешний Node-демон (@agentmemory/agentmemory на iii-sdk); maind его
ОРКЕСТРИРУЕТ (start/stop/status), а не переписывает. Порты берутся из env/конфига
(никаких хардкодов), чтобы не конфликтовать с другим узлом (например Brain).

HTTP-контракт демона: GET /health · POST /memories {namespace,type,text} ·
GET /search?namespace=&q= → {results:[{score,text}]}."""
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from core.http import HTTPUnauthorizedError

from .common import (die, http_get_json, http_post_json, parse_args, pid_alive,
                     ping, warn)
from .config import load_config
from .constants import (DIGEST_BUDGET_CHARS, DIGEST_ITEM_MAX_CHARS, DIGEST_MIN_TAIL_CHARS,
                        DIGEST_SHARED_MAX, DIGEST_TRUNCATE_SUFFIX, MEMORY_HEAVY_TIMEOUT_S,
                        MEMORY_HTTP_PORT, MEMORY_LIGHT_TIMEOUT_S, MEMORY_RETRIES,
                        MEMORY_RETRY_BACKOFF_S, MEMORY_STREAM_PORT, MEMORY_WORKERS)


# ── разрешение портов/URL (env → конфиг → дефолт) ───────────────────────────
def resolve_ports(env, config):
    """(http_port, stream_port, url). Приоритет: env (AGENTMEMORY_*) → config.memory
    → дефолты 4111/4112. URL — из AGENTMEMORY_URL или http://127.0.0.1:<http_port>."""
    mem = (config or {}).get("memory") or {}
    http_port = int(os.environ.get("AGENTMEMORY_PORT")
                    or mem.get("http_port") or MEMORY_HTTP_PORT)
    stream_port = int(os.environ.get("AGENTMEMORY_STREAM_PORT")
                      or mem.get("stream_port") or MEMORY_STREAM_PORT)
    url = (os.environ.get("AGENTMEMORY_URL") or mem.get("url")
           or f"http://127.0.0.1:{http_port}")
    return http_port, stream_port, url.rstrip("/")


def health(url):
    """True, если демон отвечает на /agentmemory/health (или /livez). Оба эндпойнта
    ВСЕГДА публичны у движка (даже с заданным AGENTMEMORY_SECRET) — это НЕ проверка
    авторизации, только «демон жив» (см. check_auth для 401 vs недоступен)."""
    return (ping(f"{url}/agentmemory/health", timeout=3)
            or ping(f"{url}/agentmemory/livez", timeout=3))


# ── роль узла (ADR-0001 п.1/п.5, D27/D80) ────────────────────────────────────
def memory_role(config):
    return ((config or {}).get("memory") or {}).get("role", "standalone")


def refuse_if_client_role(config):
    """die(), если этот узел — client: локальный демон памяти НЕ поднимается —
    второй писатель ломает единственность стора варианта 1 (ADR-0001 п.1/п.5, D27).
    Запрет — КОД, а не документация (Implementation Rules P4.2)."""
    if memory_role(config) == "client":
        die("роль узла memory.role='client' — локальный демон памяти НЕ поднимается "
            "(второй писатель ломает cross-machine память, ADR-0001). Используйте "
            "хост памяти по memory.url или смените memory.role на этой машине.")


# ── bind-адрес демона: адрес машины НЕ живёт в tracked-конфиге ───────────────────
_BIND_FORBIDDEN = {"0.0.0.0", "::", "0:0:0:0:0:0:0:0"}


def lan_address():
    """Основной LAN-IPv4 ЭТОЙ машины (UDP-connect без отправки пакетов) или None."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith("127.") else address


def resolve_bind_host(config):
    """Адрес bind для iii-http, заданный УЗЛОМ, а не репозиторием: env `AGENTMEMORY_BIND_HOST`
    → `memory.bind_host` в config.json (gitignored). `auto` — LAN-адрес текущей машины.
    None → tracked-шаблон остаётся как есть (loopback). Не-loopback допустим только для
    memory.role='host'; `0.0.0.0`/`::` запрещены (ADR-0001, D28)."""
    mem = (config or {}).get("memory") or {}
    value = (os.environ.get("AGENTMEMORY_BIND_HOST") or mem.get("bind_host") or "").strip()
    if not value:
        return None
    if value == "auto":
        value = lan_address()
        if value is None:
            die("memory.bind_host='auto': LAN-адрес этой машины не определён — задайте "
                "AGENTMEMORY_BIND_HOST/memory.bind_host явно или подключите сеть")
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        die(f"memory.bind_host='{value}' — ожидается IP-адрес или 'auto'")
    if value in _BIND_FORBIDDEN or parsed.is_unspecified:
        die("memory.bind_host: bind на все интерфейсы (0.0.0.0/::) запрещён — укажите конкретный "
            "LAN-адрес или 'auto' (ADR-0001, D28)")
    if not parsed.is_loopback and memory_role(config) != "host":
        die(f"memory.bind_host='{value}' не loopback, но memory.role != 'host' — LAN-bind "
            "включается только на host-машине памяти (ADR-0001)")
    return value


def effective_memory_config(env, config):
    """Путь iii-config для демона. Tracked-шаблон портируем (host: 127.0.0.1); адрес этой
    машины подставляется в РАНТАЙМ-копию `data/iii-config.runtime.yaml` (gitignored) —
    перенос на другой комп = поменять `memory.bind_host`/`auto`, а не править репозиторий."""
    host = resolve_bind_host(config)
    if host is None:
        return env.memory_config
    lines = env.memory_config.read_text(encoding="utf-8").splitlines()
    out, in_http, done = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- name:"):
            in_http = stripped == "- name: iii-http"
        if in_http and not done and stripped.startswith("host:"):
            line = f"{line[:len(line) - len(line.lstrip())]}host: {host}"
            done = True
        out.append(line)
    if not done:
        die(f"в {env.memory_config} не найден workers[iii-http].host — bind-адрес не подставить")
    env.data_dir.mkdir(parents=True, exist_ok=True)
    target = env.data_dir / "iii-config.runtime.yaml"
    target.write_text("# сгенерировано maind из tracked-шаблона; не править и не коммитить\n"
                      + "\n".join(out) + "\n", encoding="utf-8")
    return target


# ── аутентификация (ADR-0001 п.3/п.4, D29) ───────────────────────────────────
def resolve_secret(env, config):
    """Bearer-токен для протектед-вызовов памяти. Порядок (ADR-0001): env
    `AGENTMEMORY_SECRET` → `memory.secret_file` (путь к 0600-файлу; относительный —
    от корня узла) → нет секрета (анонимный локальный демон, как сегодня — дефолт
    не меняет ничего)."""
    env_secret = os.environ.get("AGENTMEMORY_SECRET")
    if env_secret:
        return env_secret
    secret_file = ((config or {}).get("memory") or {}).get("secret_file")
    if not secret_file:
        return None
    path = Path(os.path.expanduser(secret_file))
    if not path.is_absolute():
        path = env.root / path
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError as e:
        warn(f"memory.secret_file не читается ({path}: {e}) — вызовы памяти пойдут без токена")
        return None


def auth_headers(secret):
    """{'Authorization': 'Bearer <secret>'} либо None (без секрета — как сегодня,
    заголовки не идут вовсе)."""
    return {"Authorization": f"Bearer {secret}"} if secret else None


def check_auth(url, headers, *, timeout=MEMORY_LIGHT_TIMEOUT_S):
    """Различает «недоступен» от «неавторизован» на протектед-эндпоинте (findings
    §2: /agentmemory/health ВСЕГДА публичен и не даёт 401 — правду про bearer можно
    узнать только реальным протектед-вызовом). None — секрет не настроен (проверка
    неприменима) · True — авторизован · False — демон ответил 401."""
    if not headers:
        return None
    try:
        http_post_json(f"{url}/agentmemory/search",
                       {"query": "__maind_auth_probe__", "namespace": "__maind_auth_probe__",
                        "limit": 1}, headers=headers, timeout=timeout)
        return True
    except HTTPUnauthorizedError:
        return False
    except RuntimeError:
        return None   # недоступен/иная ошибка — не про авторизацию


def unavailable_message(config, url):
    """Роль-осознанный текст недоступности памяти (единственная точка врезки MCP,
    `_run_tool` в mcp.py): на client НЕ подсказываем поднять локальный демон — это
    инструкция создать второго писателя (findings §2 «в)»)."""
    if memory_role(config) == "client":
        return f"хост памяти {url} недоступен (роль client — локальный демон не поднимается)"
    return f"демон памяти не запущен ({url}) — maind start --only memory"


def _retry_read(fn, *, retries=MEMORY_RETRIES, backoff=MEMORY_RETRY_BACKOFF_S):
    """Ретраи ТОЛЬКО для read-путей (export/digest) — контракт `store` не несёт
    operation-id, ретрай мутации рискует дублем (ADR-0001 п.5, `research/06` §5),
    поэтому store/forget им НЕ оборачиваются. HTTPUnauthorizedError не ретраится —
    тот же токен даст тот же 401 (findings §6 — ретраи против transient-сбоя канала,
    не против авторизации)."""
    last = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except HTTPUnauthorizedError:
            raise
        except RuntimeError as e:
            last = e
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last


def _read_pid(env):
    if not env.memory_pidfile.exists():
        return None
    try:
        return int(env.memory_pidfile.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


# ── жизненный цикл демона ────────────────────────────────────────────────────
def _daemon_argv(env, config):
    """(cmd, child_env, url) для запуска Node-демона памяти. Общий для start()/run() —
    оба пути обязаны отказать на роли client (ADR-0001 п.5, D27), поэтому проверка
    здесь, а не в каждом из них по отдельности. Проверяет node и бинарь демона —
    иначе die с подсказкой."""
    refuse_if_client_role(config)
    http_port, stream_port, url = resolve_ports(env, config)
    if shutil.which("node") is None:
        die("node не найден в PATH — agent-memory это Node-демон")
    bin_path = env.root / "node_modules" / ".bin" / "agentmemory"
    if not bin_path.exists():
        die("agentmemory не установлен — выполните `npm install` в корне maind "
            "(демон памяти @agentmemory/agentmemory)")
    cmd = ["node"]
    if env.env_file.exists():
        cmd.append(f"--env-file={env.env_file}")
    cmd.append(str(bin_path))
    child_env = {
        **os.environ,
        "AGENTMEMORY_PORT": str(http_port),
        "AGENTMEMORY_STREAM_PORT": str(stream_port),
        "AGENTMEMORY_URL": url,
        "AGENTMEMORY_III_CONFIG": str(effective_memory_config(env, config)),
    }
    return cmd, child_env, url


def run_foreground(env, config):
    """Запустить демон памяти в ПЕРЕДНЕМ плане (для systemd Type=simple): exec node,
    заменяя текущий процесс — systemd трекает демон как MAINPID и сам рулит рестартом.
    При успехе НЕ возвращается."""
    cmd, child_env, _ = _daemon_argv(env, config)
    env.data_dir.mkdir(parents=True, exist_ok=True)
    # exec сохраняет PID → pidfile корректно указывает на node, и `maind memory
    # status`/`stop` видят реальный процесс (даже под управлением systemd).
    env.memory_pidfile.write_text(str(os.getpid()), encoding="utf-8")
    os.chdir(str(env.root))
    os.execvpe(cmd[0], cmd, child_env)


def start(env, config, *, detach=True, timeout_s=10):
    """Запускает Node-демон отдельной сессией, пишет pidfile, ждёт health. 0 — успех."""
    _, stream_port, url = resolve_ports(env, config)
    if health(url):
        print(f"память уже запущена: {url}")
        return 0
    env.data_dir.mkdir(parents=True, exist_ok=True)
    cmd, child_env, _ = _daemon_argv(env, config)
    log = open(env.memory_log, "ab")
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(env.root), env=child_env,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=detach)
    finally:
        log.close()
    env.memory_pidfile.write_text(str(proc.pid), encoding="utf-8")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if health(url):
            print(f"память запущена: {url} (pid {proc.pid}, stream :{stream_port}, "
                  f"service maind)")
            return 0
        if proc.poll() is not None:
            die(f"демон памяти завершился сразу (код {proc.returncode}) — "
                f"см. лог {env.memory_log}")
        time.sleep(0.5)
    die(f"память не поднялась за {timeout_s}s на {url} — проверьте порт/конфиг, "
        f"см. лог {env.memory_log}")


def stop(env, config, *, timeout_s=5):
    """Останавливает демон, запущенный через maind (SIGTERM→SIGKILL). Чужой не трогает."""
    _, _, url = resolve_ports(env, config)
    pid = _read_pid(env)
    if pid is None:
        if health(url):
            warn(f"демон отвечает на {url}, но запущен не через maind (нет pidfile) — "
                 f"не останавливаю чужой процесс")
        else:
            print("память не запущена")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        env.memory_pidfile.unlink(missing_ok=True)
        print("процесс уже мёртв — pidfile очищен")
        return 0
    deadline = time.time() + timeout_s
    while time.time() < deadline and health(url):
        time.sleep(0.3)
    if health(url):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass  # процесс уже исчез между health-проверкой и SIGKILL — это и была цель
    env.memory_pidfile.unlink(missing_ok=True)
    print(f"память остановлена (pid {pid})")
    return 0


def status(env, config):
    """Снимок состояния памяти для status/doctor/MCP."""
    http_port, stream_port, url = resolve_ports(env, config)
    pid = _read_pid(env)
    running = health(url)
    alive = pid_alive(pid) if pid is not None else None
    return {
        "running": running,
        "url": url,
        "http_port": http_port,
        "stream_port": stream_port,
        "pid": pid,
        "pid_alive": alive,
        "pidfile_stale": pid is not None and alive is False,
        "owned": pid is not None,
        "workers": [{"name": w, "state": "up" if running else "down"}
                    for w in MEMORY_WORKERS],
        "stream_up": ping(f"http://127.0.0.1:{stream_port}/", timeout=2)
        if running else False,
    }


# ── HTTP-обёртка со scope'ами + ИЗОЛЯЦИЯ НА СТОРОНЕ maind ─────────────────────
# agentmemory 0.9.x: REST под префиксом /agentmemory/* (сверено с живым демоном).
#
# ВАЖНО: демон — ЕДИНЫЙ глобальный пул. Эмпирически (живой curl) поле `namespace`
# в remember/search/list ИГНОРИРУЕТСЯ, а `type` демон ПЕРЕОПРЕДЕЛЯЕТ (classifier).
# Дословно сохраняется только `content`. Поэтому изоляцию по scope обеспечивает САМ
# maind: при записи встраиваем scope-маркер в начало контента, при чтении — фильтруем
# результаты по маркеру и снимаем его. Это единственный надёжный канал на этой версии
# движка (см. docs/maind/guide/federation.md — «изоляция на стороне maind»).
SCOPE_MARK_RE = re.compile(r"^\[\[s:(?P<scope>[^\]]+)\]\]\s?")
# Кандидатов из ГЛОБАЛЬНОГО пула до фильтра по scope. Пул общий на все проекты экосистемы
# (17+), поэтому маленькое окно вытесняло релевантные факты нужного scope чужими (crowding).
# Берём шире; при насыщении (демон вернул ровно лимит) предупреждаем — факты могли не влезть.
RECALL_LIMIT = 200
# Кап для shared-scope'ов (ns:*/global) при project:<id>-expansion в _recall_union (mcp.py):
# без него один общий ns: (напр. ns:axioma, 47 записей) забивал ответ и вытеснял приватный
# scope проекта (напр. 2 записи) — измерено на 6 проектах, 84-96% ответа из shared
# (roadmap/memory-recall-shared-namespace-priority). Приватный scope остаётся без капа
# (RECALL_LIMIT) — recall целенаправленный, не пассивный SessionStart-инжект (в отличие от
# дайджеста, где shared_max=0 режет shared в ноль, см. DIGEST_SHARED_MAX/select_digest_items).
RECALL_SHARED_LIMIT = 40


def mark_scope(scope, value):
    """Встроить scope-маркер в начало контента: единственный канал, который демон
    сохраняет дословно (namespace игнорит, type переопределяет)."""
    return f"[[s:{scope}]] {value}"


def split_scope(text):
    """(scope|None, чистый_текст) из контента. scope — ВЛАДЕЛЕЦ (первый маркер; его ставит
    mark_scope при записи, подделать нельзя). Снимаем ВСЕ ведущие маркеры `[[s:…]]` — на случай
    вложенных/повторных в контенте, чтобы marker-артефакты не утекали в выдачу. Немаркированный
    (легаси/чужой) → (None, text)."""
    m = SCOPE_MARK_RE.match(text or "")
    if not m:
        return None, text
    owner, rest = m.group("scope"), text[m.end():]
    while True:                       # снять остаточные ведущие маркеры (владельца не меняем)
        m2 = SCOPE_MARK_RE.match(rest)
        if not m2:
            return owner, rest
        rest = rest[m2.end():]


def store(url, scope, key, value, headers=None):
    """Сохранить факт: POST /agentmemory/remember. scope встраивается в КОНТЕНТ маркером
    `[[s:<scope>]]` (демон игнорит namespace и переопределяет type — это единственный
    надёжный канал изоляции на стороне maind). `namespace`/`type` шлём как было — на
    будущее, если движок начнёт их уважать. `headers` — bearer-аутентификация (ADR-0001),
    без секрета не передаются вовсе (дефолт не меняет ничего)."""
    return http_post_json(f"{url}/agentmemory/remember",
                          {"namespace": scope, "content": mark_scope(scope, value),
                           "type": key}, headers=headers)


EPHEMERAL_KEYS = {"progress", "plan-progress", "checkpoint", "session-log"}
ACTIVE_HANDOFF_MARKER = "[active-handoff]"


def store_managed(url, scope, key, value, headers=None):
    """Apply the durable-memory write policy before storing a fact.

    Session/checkpoint journals belong in repository artifacts.  ``active-handoff``
    is the single mutable continuity slot and is replaced atomically enough for the
    underlying append-only engine (forget old slots, then write one current value).
    """
    normalized = (key or "fact").strip().lower()
    if normalized in EPHEMERAL_KEYS:
        raise ValueError("ephemeral progress is not durable memory; update the repository "
                         "handoff or use key=active-handoff")
    if normalized != "active-handoff":
        return store(url, scope, key, value, headers=headers)
    text = value if value.startswith(ACTIVE_HANDOFF_MARKER) else \
        f"{ACTIVE_HANDOFF_MARKER} {value}"
    for item in export(url, scope, headers):
        raw = item.get("content") or item.get("narrative") or item.get("title") or ""
        owner, clean = split_scope(raw)
        if owner == scope and (clean or "").startswith(ACTIVE_HANDOFF_MARKER):
            mid = item.get("id")
            if mid:
                forget(url, scope, mid, headers=headers)
    return store(url, scope, "active-handoff", text, headers=headers)


def recall(url, scope, query, limit=RECALL_LIMIT, headers=None):
    """Поиск С ИЗОЛЯЦИЕЙ: демон ищет по ГЛОБАЛЬНОМУ пулу (namespace не фильтрует),
    поэтому берём широкий топ и оставляем ТОЛЬКО факты запрошенного `scope` по маркеру
    в контенте; маркер из текста снимаем. Немаркированные факты (легаси) — режем."""
    res = http_post_json(f"{url}/agentmemory/search",
                         {"query": query, "namespace": scope, "limit": limit}, headers=headers)
    results = res.get("results", []) if isinstance(res, dict) else []
    out = []
    for r in results:
        obs = r.get("observation") or {}
        raw = (obs.get("narrative") or obs.get("title")
               or " ".join(obs.get("facts") or []))
        sc, text = split_scope(raw)
        if sc != scope:           # чужой scope или немаркированный легаси → изолируем
            continue
        out.append({"score": r.get("score"), "text": text, "id": obs.get("id")})
    # Насыщение: демон вернул ровно весь candidate-пул (общий на все проекты) — релевантные
    # факты scope могли не попасть в окно. Сообщаем, чтобы сузить запрос/поднять лимит.
    if len(results) >= limit:
        warn(f"recall: candidate-пул насыщен ({limit}) — часть фактов scope '{scope}' могла "
             f"не влезть; сузьте запрос или поднимите limit.")
    return out


def forget(url, scope, key, headers=None):
    """Удалить факт по memoryId: POST /agentmemory/forget {memoryId}.

    agentmemory 0.9.x ждёт ИМЕННО `memoryId` (id памяти глобально уникален);
    прежний payload {namespace, id} давал HTTP 400 (сверено живым curl к демону).
    scope сохранён в сигнатуре для совместимости вызовов, но в запрос не идёт.
    """
    try:
        return http_post_json(f"{url}/agentmemory/forget", {"memoryId": key}, headers=headers)
    except HTTPUnauthorizedError:
        raise
    except RuntimeError as e:
        raise RuntimeError(f"forget: {e}") from e


def export(url, scope, headers=None, *, timeout=MEMORY_HEAVY_TIMEOUT_S, retries=MEMORY_RETRIES):
    """Дамп памяти scope: GET /agentmemory/memories?namespace= (весь ГЛОБАЛЬНЫЙ пул —
    namespace демон игнорит). Самый дорогой по каналу вызов (SessionStart-дайджест
    тянет его целиком, research/06 §4) — настраиваемый таймаут/ретраи (measured:
    findings/P4.2-remote-link-measure.md); ретраится (read, не мутация)."""
    def _do():
        return http_get_json(f"{url}/agentmemory/memories?namespace={quote(scope)}",
                             timeout=timeout, headers=headers)
    res = _retry_read(_do, retries=retries)
    return res.get("memories", []) if isinstance(res, dict) else []


def memory_owner_scope(url, memory_id, scopes, headers=None):
    """Best-effort: scope-владелец факта `memory_id` среди `scopes` — по маркеру
    `[[s:<scope>]]` в контенте (а нет маркера → бакету, в котором найден), или None,
    если факт не найден ни в одном scope. Нужен forget'у: memoryId глобально уникален,
    демон удаляет по нему БЕЗ оглядки на scope, поэтому до удаления подтверждаем, что
    факт действительно принадлежит разрешённому проекту (защита кросс-namespace
    удаления). Устойчив к форме элемента дампа (raw `content` или observation)."""
    for sc in scopes:
        for m in export(url, sc, headers):
            if str(m.get("id")) != str(memory_id):
                continue
            obs = m.get("observation") or m
            raw = (m.get("content") or obs.get("narrative") or obs.get("title")
                   or " ".join(obs.get("facts") or []))
            marker, _ = split_scope(raw)
            return marker or sc
    return None


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_memory(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind memory <start|run|stop|status|remember|recall|forget|count|digest> ...")
        return
    sub, rest = argv[0], argv[1:]
    config, _src = load_config(env)
    if sub == "start":
        start(env, config)
    elif sub == "run":
        run_foreground(env, config)  # foreground для systemd (exec, не возвращается)
    elif sub == "stop":
        stop(env, config)
    elif sub == "status":
        _cmd_status(env, config, rest)
    elif sub == "remember":
        _cmd_remember(env, config, rest)
    elif sub == "recall":
        _cmd_recall(env, config, rest)
    elif sub == "forget":
        _cmd_forget(env, config, rest)
    elif sub == "count":
        _cmd_count(env, config, rest)
    elif sub == "digest":
        _cmd_digest(env, config, rest)
    else:
        die(f"неизвестная подкоманда memory: {sub} "
            "(start|stop|status|remember|recall|forget|count|digest)")


# ── память: scope-aware CLI (единый путь для хука и человека) ─────────────────
# remember/recall/forget считают scope из конфига проекта через namespaces.py —
# тот же источник истины, что у MCP и seed. Хук памяти делегирует сюда (modes/maind.sh),
# поэтому «запомнил» (хук) и «вспомнил» (MCP/CLI) гарантированно идут в один стор.
def _memory_target(env, config, opts):
    """(project|None, write_scopes, read_scopes). --scope = raw-режим без проекта."""
    from .namespaces import find as ns_find
    from .namespaces import group_scopes, private_scope, recall_scopes
    from .projects import match_cwd
    raw = opts.get("scope")
    if raw:
        return None, [raw], [raw]
    pid = opts.get("project")
    if pid:
        proj = ns_find(config, pid)
        if not proj:
            die(f"проект не найден в config.json: {pid}")
    else:
        proj = match_cwd(env, config)
        if not proj:
            die("не определить проект из cwd — укажи --project <id> или --scope <scope>")
    write = [private_scope(proj)]
    if opts.get("share"):                 # --share → ещё и в общие бакеты группы (ns:<тег>)
        for s in group_scopes(proj):
            if s not in write:
                write.append(s)
    return proj, write, recall_scopes(proj)


def _require_daemon(env, config):
    """(url, headers) — headers несёт bearer, если секрет настроен (ADR-0001)."""
    _, _, url = resolve_ports(env, config)
    if not health(url):
        die(f"демон памяти не запущен ({url}) — подними: maind start --only memory")
    return url, auth_headers(resolve_secret(env, config))


def _cmd_remember(env, config, argv):
    opts, pos = parse_args(argv, {"--project": "str", "--scope": "str", "--share": "bool",
                                  "--type": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print('maind memory remember [--project ID | --scope S] [--share] [--type T] "<факт>"')
        return
    url, headers = _require_daemon(env, config)
    _proj, write_scopes, _read = _memory_target(env, config, opts)
    key = opts.get("type") or "fact"
    written = []
    for sc in write_scopes:
        try:
            res = store_managed(url, sc, key, pos[0], headers=headers)
        except ValueError as e:
            die(str(e))
        mid = (res.get("memory") or {}).get("id") if isinstance(res, dict) else None
        written.append({"scope": sc, "id": mid})
    if opts["json"]:
        print(json.dumps({"written": written}, ensure_ascii=False))
    else:
        print("memory(maind): записано → " + ", ".join(w["scope"] for w in written))


def _cmd_recall(env, config, argv):
    opts, pos = parse_args(argv, {"--project": "str", "--scope": "str",
                                  "--limit": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print('maind memory recall [--project ID | --scope S] [--limit N] "<запрос>"')
        return
    try:
        limit = int(opts.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    url, headers = _require_daemon(env, config)
    _proj, _write, read_scopes = _memory_target(env, config, opts)
    seen, merged = set(), []
    for sc in read_scopes:                # union по приватному + ns:<тег> + global
        for r in recall(url, sc, pos[0], headers=headers):
            text = r.get("text")          # один факт, всплывший в неск. scope'ах — раз
            if text in seen:
                continue
            seen.add(text)
            merged.append({**r, "scope": sc})
    merged.sort(key=lambda r: r.get("score") or 0, reverse=True)
    merged = merged[:limit]
    if opts["json"]:
        print(json.dumps(merged, ensure_ascii=False))
    elif not merged:
        print("memory(maind): ничего не найдено")
    else:
        for r in merged:
            print(f"— [{r.get('score')}] {r.get('text')}  ({r.get('scope')})")


def _cmd_forget(env, config, argv):
    opts, pos = parse_args(argv, {"--project": "str", "--scope": "str",
                                  "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("maind memory forget [--project ID] <memoryId>   # id памяти глобально уникален")
        return
    url, headers = _require_daemon(env, config)
    res = forget(url, None, pos[0], headers=headers)
    if opts["json"]:
        print(json.dumps(res, ensure_ascii=False))
    else:
        deleted = res.get("deleted") if isinstance(res, dict) else None
        print(f"memory(maind): forget {pos[0]} → deleted={deleted}")


def _truncate_item(text, max_chars):
    """Обрезать `text` до `max_chars` по последнему пробелу + суффикс DIGEST_TRUNCATE_SUFFIX.
    Не режет посреди слова (кроме вырожденного случая — суффикс сам не влезает в max_chars)."""
    if len(text) <= max_chars:
        return text
    room = max_chars - len(DIGEST_TRUNCATE_SUFFIX)
    if room <= 0:
        return text[:max_chars]
    cut = text[:room]
    sp = cut.rfind(" ")
    if sp > 0:
        cut = cut[:sp]
    return cut + DIGEST_TRUNCATE_SUFFIX


def select_digest_items(raw, private, want, *, limit, budget_chars, item_max_chars, shared_max):
    """Чистая функция (без I/O/Env) — отбор фактов для SessionStart-дайджеста из сырого
    дампа памяти `raw` (список dict export()-формы: content/narrative/title + timestamp).

    `private` — приватный scope проекта (первым в выдаче); `want` — видимые scope'ы
    (приватный + ns:*/global по recall_scopes). Алгоритм (2026.07.12-CONTEXT-ECONOMY D10, P1.1):
    1) фильтр по scope-маркеру/want + дедуп + ecosystem-link cross-ref (как раньше) →
       партиция private_rows/shared_rows, каждая отсортирована свежее-сверху;
    2) кандидаты = весь private + shared[:shared_max] (дефолт shared_max=0 → shared не
       участвует вовсе — project-only digest, D10);
    3) каждый кандидат обрезается до item_max_chars (по слову + суффикс);
    4) аккумулируются до budget_chars: переполняющий item обрезается до остатка бюджета,
       если остаток ≥ DIGEST_MIN_TAIL_CHARS, иначе — дропается;
    5) финально — count-cap `limit`;
    6) возвращает (items, dropped) — dropped = сколько фактов из видимого пула (private+shared,
       без учёта cap'а до этого) не попало в итог (обрезано целиком/лимитом/бюджетом).

    Возвращает (items: list[str], dropped: int)."""
    seen, priv_rows, shared_rows = set(), [], []
    for m in raw:
        text = m.get("content") or m.get("narrative") or m.get("title") or ""
        sc, clean = split_scope(text)
        clean = (clean or "").strip()
        if sc not in want or not clean or clean in seen:
            continue
        # чужие seed-cross-ref'ы ("[maind:ecosystem-link] a → b") — graph-сиды, не контекст
        if sc != private and clean.startswith("[maind:ecosystem-link]") and " → " in clean:
            continue
        seen.add(clean)
        ts = m.get("timestamp") or ""
        (priv_rows if sc == private else shared_rows).append((ts, clean))
    priv_rows.sort(key=lambda r: r[0], reverse=True)     # свежее сверху
    shared_rows.sort(key=lambda r: r[0], reverse=True)
    total_pool = len(priv_rows) + len(shared_rows)
    shared_cap = shared_rows[:shared_max] if shared_max > 0 else []
    candidates = [c for _, c in priv_rows] + [c for _, c in shared_cap]

    items, used = [], 0
    for cand in candidates:
        cand = _truncate_item(cand, item_max_chars)
        if used + len(cand) <= budget_chars:
            items.append(cand)
            used += len(cand)
            continue
        remaining = budget_chars - used
        if remaining >= DIGEST_MIN_TAIL_CHARS:
            items.append(_truncate_item(cand, remaining))
            used = budget_chars
        # иначе — молча дропаем (учтётся в dropped ниже), пробуем следующего кандидата
    items = items[:limit]
    dropped = total_pool - len(items)
    return items, dropped


def _cmd_digest(env, config, argv):
    """Компактный дайджест памяти проекта для SessionStart-хука (additionalContext).
    ДЕТЕРМИНИРОВАННО (не семантика): берём ВСЕ факты scope'ов проекта через list+фильтр по
    scope-маркеру, приоритет приватному, свежее сверху, байт-бюджет (2026.07.12-CONTEXT-ECONOMY D10, P1.1) — по
    умолчанию project-only (shared_max=0), shared — явно флагом/конфигом. ХУК-БЕЗОПАСНО:
    демон лёг / scope не определён → молча пусто, без die."""
    opts, _ = parse_args(argv, {"--project": "str", "--scope": "str", "--limit": "str",
                                "--budget-chars": "str", "--item-max": "str",
                                "--shared-max": "str", "--json": "bool"}, max_pos=0)
    if opts["help"]:
        print("maind memory digest [--project ID|--scope S] [--limit N] [--budget-chars N] "
              "[--item-max N] [--shared-max N]  # дайджест для SessionStart")
        return
    dg = (config.get("memory") or {}).get("digest") or {}
    try:
        limit = int(opts.get("limit") or 8)
    except (TypeError, ValueError):
        limit = 8
    try:
        budget_chars = int(opts.get("budget_chars") or dg.get("budget_chars") or DIGEST_BUDGET_CHARS)
    except (TypeError, ValueError):
        budget_chars = DIGEST_BUDGET_CHARS
    try:
        item_max_chars = int(opts.get("item_max") or dg.get("item_max_chars") or DIGEST_ITEM_MAX_CHARS)
    except (TypeError, ValueError):
        item_max_chars = DIGEST_ITEM_MAX_CHARS
    try:
        shared_max = int(opts.get("shared_max") or dg.get("shared_max", DIGEST_SHARED_MAX))
    except (TypeError, ValueError):
        shared_max = DIGEST_SHARED_MAX
    try:
        timeout_s = float(dg.get("timeout_s") or MEMORY_HEAVY_TIMEOUT_S)
    except (TypeError, ValueError):
        timeout_s = MEMORY_HEAVY_TIMEOUT_S
    try:
        retries = int(dg["retries"]) if dg.get("retries") is not None else MEMORY_RETRIES
    except (TypeError, ValueError):
        retries = MEMORY_RETRIES
    _, _, url = resolve_ports(env, config)
    if not health(url):
        return                                   # демон лёг → тихо (хук-безопасно)
    try:
        proj, _w, read_scopes = _memory_target(env, config, opts)
    except SystemExit:
        return                                   # scope не определён → тихо
    private = read_scopes[0] if read_scopes else None
    want = set(read_scopes)
    headers = auth_headers(resolve_secret(env, config))
    try:                                         # весь пул (namespace игнор) → фильтр по маркеру
        raw = export(url, "", headers, timeout=timeout_s, retries=retries)
    except RuntimeError:
        return
    items, dropped = select_digest_items(raw, private, want, limit=limit,
                                         budget_chars=budget_chars,
                                         item_max_chars=item_max_chars,
                                         shared_max=shared_max)
    if not items:
        return
    if opts["json"]:
        print(json.dumps(items, ensure_ascii=False))
        return
    pid = proj["id"] if proj else (opts.get("scope") or "?")
    print(f"Память проекта {pid} (mAInd — детали: `maind memory recall \"<тема>\"`):")
    for t in items:
        print(f"- {t}")
    if shared_max == 0:
        # D10: project-only дефолт — межпроектное поднимается явно, не проглатывается в digest
        print("  (межпроектное: maind memory recall --scope ns:<name> — digest project-only)")
    if dropped > 0:
        print(f"  (+{dropped} фактов — maind memory recall)")


def _cmd_count(env, config, argv):
    """Сколько фактов в памяти проекта по scope'ам (приватный + ns:<тег> + global) — наблюдаемость
    «наполнена ли память». Считаем по scope-МАРКЕРУ в контенте, как recall/digest: демон-пул общий и
    namespace не фильтрует, поэтому export('') даёт весь пул, а принадлежность scope'у решает маркер
    (иначе посчитали бы факты всех проектов экосистемы)."""
    opts, _ = parse_args(argv, {"--project": "str", "--scope": "str", "--json": "bool"}, max_pos=0)
    if opts["help"]:
        print("maind memory count [--project ID | --scope S] [--json]  "
              "# сколько фактов в памяти по scope")
        return
    url, headers = _require_daemon(env, config)
    proj, _write, read_scopes = _memory_target(env, config, opts)
    try:
        raw = export(url, "", headers)            # весь пул (namespace игнор) → фильтр по маркеру
    except RuntimeError as e:
        die(f"не прочитать память: {e}")
    per = {sc: 0 for sc in read_scopes}
    seen = set()
    for m in raw:
        text = m.get("content") or m.get("narrative") or m.get("title") or ""
        sc, clean = split_scope(text)
        if sc in per:
            per[sc] += 1
            clean = (clean or "").strip()
            if clean:
                seen.add(clean)
    total_unique = len(seen)
    if opts["json"]:
        print(json.dumps({"scopes": per, "total_unique": total_unique}, ensure_ascii=False))
        return
    pid = proj["id"] if proj else (opts.get("scope") or "?")
    parts = ", ".join(f"{sc}={n}" for sc, n in per.items())
    print(f"Память проекта {pid}: {parts} (уникальных {total_unique})")


def _cmd_status(env, config, argv):
    opts, _ = parse_args(argv, {"--json": "bool"})
    st = status(env, config)
    if opts["json"]:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return
    state = "запущена" if st["running"] else "остановлена"
    print(f"Память: {state} — {st['url']} "
          f"(http :{st['http_port']}, stream :{st['stream_port']})")
    if st["pid"]:
        tail = "" if st["pid_alive"] else "  [pidfile устарел]"
        print(f"  pid {st['pid']}{tail}")
    elif st["running"]:
        print("  запущена не через maind (нет pidfile)")
    print("  воркеры: " + ", ".join(f"{w['name']}={w['state']}" for w in st["workers"]))
