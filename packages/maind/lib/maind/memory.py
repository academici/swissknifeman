"""Память узла: жизненный цикл agent-memory демона + HTTP-обёртка со scope'ами.

agent-memory — внешний Node-демон (@agentmemory/agentmemory на iii-sdk); maind его
ОРКЕСТРИРУЕТ (start/stop/status), а не переписывает. Порты берутся из env/конфига
(никаких хардкодов), чтобы не конфликтовать с другим узлом (например Brain).

HTTP-контракт демона: GET /health · POST /memories {namespace,type,text} ·
GET /search?namespace=&q= → {results:[{score,text}]}."""
import json
import os
import re
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
def _daemon_argv(env, config):
    """(cmd, child_env, url) для запуска Node-демона памяти. Общий для start()/run().
    Проверяет node и бинарь демона — иначе die с подсказкой."""
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
        "AGENTMEMORY_III_CONFIG": str(env.memory_config),
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
RECALL_LIMIT = 50  # кандидатов из глобального пула до фильтра по scope


def mark_scope(scope, value):
    """Встроить scope-маркер в начало контента: единственный канал, который демон
    сохраняет дословно (namespace игнорит, type переопределяет)."""
    return f"[[s:{scope}]] {value}"


def split_scope(text):
    """(scope|None, чистый_текст) из контента. Немаркированный (старый/чужой) → (None, text)."""
    m = SCOPE_MARK_RE.match(text or "")
    if not m:
        return None, text
    return m.group("scope"), text[m.end():]


def store(url, scope, key, value):
    """Сохранить факт: POST /agentmemory/remember. scope встраивается в КОНТЕНТ маркером
    `[[s:<scope>]]` (демон игнорит namespace и переопределяет type — это единственный
    надёжный канал изоляции на стороне maind). `namespace`/`type` шлём как было — на
    будущее, если движок начнёт их уважать."""
    return http_post_json(f"{url}/agentmemory/remember",
                          {"namespace": scope, "content": mark_scope(scope, value),
                           "type": key})


def recall(url, scope, query, limit=RECALL_LIMIT):
    """Поиск С ИЗОЛЯЦИЕЙ: демон ищет по ГЛОБАЛЬНОМУ пулу (namespace не фильтрует),
    поэтому берём широкий топ и оставляем ТОЛЬКО факты запрошенного `scope` по маркеру
    в контенте; маркер из текста снимаем. Немаркированные факты (легаси) — режем."""
    res = http_post_json(f"{url}/agentmemory/search",
                         {"query": query, "namespace": scope, "limit": limit})
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
    return out


def forget(url, scope, key):
    """Удалить факт по memoryId: POST /agentmemory/forget {memoryId}.

    agentmemory 0.9.x ждёт ИМЕННО `memoryId` (id памяти глобально уникален);
    прежний payload {namespace, id} давал HTTP 400 (сверено живым curl к демону).
    scope сохранён в сигнатуре для совместимости вызовов, но в запрос не идёт.
    """
    try:
        return http_post_json(f"{url}/agentmemory/forget", {"memoryId": key})
    except RuntimeError as e:
        raise RuntimeError(f"forget: {e}") from e


def export(url, scope):
    """Дамп памяти scope: GET /agentmemory/memories?namespace=."""
    res = http_get_json(f"{url}/agentmemory/memories?namespace={quote(scope)}")
    return res.get("memories", []) if isinstance(res, dict) else []


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_memory(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind memory <start|run|stop|status|remember|recall|forget> ...")
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
    elif sub == "digest":
        _cmd_digest(env, config, rest)
    else:
        die(f"неизвестная подкоманда memory: {sub} "
            "(start|stop|status|remember|recall|forget|digest)")


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
    _, _, url = resolve_ports(env, config)
    if not health(url):
        die(f"демон памяти не запущен ({url}) — подними: maind start --only memory")
    return url


def _cmd_remember(env, config, argv):
    opts, pos = parse_args(argv, {"--project": "str", "--scope": "str", "--share": "bool",
                                  "--type": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print('maind memory remember [--project ID | --scope S] [--share] [--type T] "<факт>"')
        return
    url = _require_daemon(env, config)
    _proj, write_scopes, _read = _memory_target(env, config, opts)
    key = opts.get("type") or "fact"
    written = []
    for sc in write_scopes:
        res = store(url, sc, key, pos[0])
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
    url = _require_daemon(env, config)
    _proj, _write, read_scopes = _memory_target(env, config, opts)
    seen, merged = set(), []
    for sc in read_scopes:                # union по приватному + ns:<тег> + global
        for r in recall(url, sc, pos[0]):
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
    url = _require_daemon(env, config)
    res = forget(url, None, pos[0])
    if opts["json"]:
        print(json.dumps(res, ensure_ascii=False))
    else:
        deleted = res.get("deleted") if isinstance(res, dict) else None
        print(f"memory(maind): forget {pos[0]} → deleted={deleted}")


def _cmd_digest(env, config, argv):
    """Компактный дайджест памяти проекта для SessionStart-хука (additionalContext).
    ДЕТЕРМИНИРОВАННО (не семантика): берём ВСЕ факты scope'ов проекта через list+фильтр по
    scope-маркеру, приоритет приватному, свежее сверху. ХУК-БЕЗОПАСНО: демон лёг / scope не
    определён → молча пусто, без die. Так maind получает свойство авто-загрузки native-памяти."""
    opts, _ = parse_args(argv, {"--project": "str", "--scope": "str",
                                "--limit": "str", "--json": "bool"}, max_pos=0)
    if opts["help"]:
        print("maind memory digest [--project ID|--scope S] [--limit N]  # дайджест для SessionStart")
        return
    try:
        limit = int(opts.get("limit") or 8)
    except (TypeError, ValueError):
        limit = 8
    _, _, url = resolve_ports(env, config)
    if not health(url):
        return                                   # демон лёг → тихо (хук-безопасно)
    try:
        proj, _w, read_scopes = _memory_target(env, config, opts)
    except SystemExit:
        return                                   # scope не определён → тихо
    private = read_scopes[0] if read_scopes else None
    want = set(read_scopes)
    try:
        raw = export(url, "")                    # весь пул (namespace игнор) → фильтр по маркеру
    except RuntimeError:
        return
    seen, rows = set(), []
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
        rows.append((0 if sc == private else 1, m.get("timestamp") or "", clean))
    rows.sort(key=lambda r: r[1], reverse=True)  # свежее сверху
    rows.sort(key=lambda r: r[0])                # приватный scope первым (стабильно)
    items = [r[2] for r in rows[:limit]]
    if not items:
        return
    if opts["json"]:
        print(json.dumps(items, ensure_ascii=False))
        return
    pid = proj["id"] if proj else (opts.get("scope") or "?")
    print(f"Память проекта {pid} (mAInd — детали: `maind memory recall \"<тема>\"`):")
    for t in items:
        print(f"- {t}")


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
