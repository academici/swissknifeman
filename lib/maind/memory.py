"""Память узла: жизненный цикл agent-memory демона + HTTP-обёртка со scope'ами.

agent-memory — внешний Node-демон (@agentmemory/agentmemory на iii-sdk); maind его
ОРКЕСТРИРУЕТ (start/stop/status), а не переписывает. Порты берутся из env/конфига
(никаких хардкодов), чтобы не конфликтовать с другим узлом (например Brain).

HTTP-контракт демона: GET /health · POST /memories {namespace,type,text} ·
GET /search?namespace=&q= → {results:[{score,text}]}."""
import json
import os
import shutil
import signal
import subprocess
import time
from urllib.parse import quote

from .common import (die, http_get_json, http_post_json, parse_args, ping, warn)
from .config import load_config
from .constants import MEMORY_HTTP_PORT, MEMORY_STREAM_PORT, MEMORY_WORKERS


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
    """True, если демон отвечает на /agentmemory/health (или /livez)."""
    return (ping(f"{url}/agentmemory/health", timeout=3)
            or ping(f"{url}/agentmemory/livez", timeout=3))


def _read_pid(env):
    if not env.memory_pidfile.exists():
        return None
    try:
        return int(env.memory_pidfile.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _pid_alive(pid):
    if not pid:
        return None
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, ValueError, OverflowError):
        return True


# ── жизненный цикл демона ────────────────────────────────────────────────────
def start(env, config, *, detach=True, timeout_s=10):
    """Запускает Node-демон отдельной сессией, пишет pidfile, ждёт health. 0 — успех."""
    http_port, stream_port, url = resolve_ports(env, config)
    if health(url):
        print(f"память уже запущена: {url}")
        return 0
    if shutil.which("node") is None:
        die("node не найден в PATH — agent-memory это Node-демон")
    bin_path = env.root / "node_modules" / ".bin" / "agentmemory"
    if not bin_path.exists():
        die("agentmemory не установлен — выполните `npm install` в корне maind "
            "(демон памяти @agentmemory/agentmemory)")

    env.data_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["node"]
    if env.env_file.exists():
        cmd.append(f"--env-file={env.env_file}")
    cmd.append(str(bin_path))
    child_env = {
        **os.environ,
        "AGENTMEMORY_PORT": str(http_port),
        "AGENTMEMORY_STREAM_PORT": str(stream_port),
        "AGENTMEMORY_URL": url,
        "AGENTMEMORY_III_CONFIG": str(env.memory_config),
    }
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
            pass
    env.memory_pidfile.unlink(missing_ok=True)
    print(f"память остановлена (pid {pid})")
    return 0


def status(env, config):
    """Снимок состояния памяти для status/doctor/MCP."""
    http_port, stream_port, url = resolve_ports(env, config)
    pid = _read_pid(env)
    running = health(url)
    pid_alive = _pid_alive(pid) if pid is not None else None
    return {
        "running": running,
        "url": url,
        "http_port": http_port,
        "stream_port": stream_port,
        "pid": pid,
        "pid_alive": pid_alive,
        "pidfile_stale": pid is not None and pid_alive is False,
        "owned": pid is not None,
        "workers": [{"name": w, "state": "up" if running else "down"}
                    for w in MEMORY_WORKERS],
        "stream_up": ping(f"http://127.0.0.1:{stream_port}/", timeout=2)
        if running else False,
    }


# ── HTTP-обёртка со scope'ами ────────────────────────────────────────────────
# agentmemory 0.9.x: REST под префиксом /agentmemory/* (сверено с живым демоном).
def store(url, scope, key, value):
    """Сохранить факт: POST /agentmemory/remember {namespace, content, type}."""
    return http_post_json(f"{url}/agentmemory/remember",
                          {"namespace": scope, "content": value, "type": key})


def recall(url, scope, query):
    """Поиск: POST /agentmemory/search {query, namespace} → [{score, text, id}]."""
    res = http_post_json(f"{url}/agentmemory/search",
                         {"query": query, "namespace": scope})
    results = res.get("results", []) if isinstance(res, dict) else []
    out = []
    for r in results:
        obs = r.get("observation") or {}
        text = (obs.get("narrative") or obs.get("title")
                or " ".join(obs.get("facts") or []))
        out.append({"score": r.get("score"), "text": text, "id": obs.get("id")})
    return out


def forget(url, scope, key):
    """Удалить факт по id (best-effort): POST /agentmemory/forget."""
    try:
        return http_post_json(f"{url}/agentmemory/forget",
                              {"namespace": scope, "id": key})
    except RuntimeError as e:
        raise RuntimeError(f"forget: {e}") from e


def export(url, scope):
    """Дамп памяти scope: GET /agentmemory/memories?namespace=."""
    res = http_get_json(f"{url}/agentmemory/memories?namespace={quote(scope)}")
    return res.get("memories", []) if isinstance(res, dict) else []


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_memory(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind memory <start|stop|status> [--json]")
        return
    sub, rest = argv[0], argv[1:]
    config, _src = load_config(env)
    if sub == "start":
        start(env, config)
    elif sub == "stop":
        stop(env, config)
    elif sub == "status":
        _cmd_status(env, config, rest)
    else:
        die(f"неизвестная подкоманда memory: {sub} (start|stop|status)")


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
