"""doctor — диагностика окружения узла maind."""
import shutil
import sys

from .common import parse_args
from .memory import health, resolve_ports


def cmd_doctor(env, argv):
    opts, _ = parse_args(argv, {"--quiet": "bool"})
    if opts["help"]:
        print("maind doctor [--quiet] — проверка окружения узла")
        return
    quiet = opts["quiet"]
    issues = 0

    def check(ok, label, hint=""):
        nonlocal issues
        if not ok:
            issues += 1
        if not quiet or not ok:
            mark = "ok " if ok else "FAIL"
            print(f"  [{mark}] {label}" + (f" — {hint}" if hint and not ok else ""))

    print(f"maind doctor (узел: {env.root})")
    check(sys.version_info >= (3, 8), f"python3 {sys.version.split()[0]}")
    check(shutil.which("node") is not None, "node в PATH",
          "agent-memory — Node-демон; установите Node.js")

    am = env.root / "node_modules" / ".bin" / "agentmemory"
    check(am.exists(), "agentmemory установлен",
          "npm install в корне maind (демон памяти @agentmemory/agentmemory)")
    check(env.memory_config.is_file(), "config/memory/iii-config.yaml на месте",
          "maind migrate from-agentmemory <путь к .agentmemory>")

    try:
        env.state_dir.mkdir(parents=True, exist_ok=True)
        probe = env.state_dir / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    check(writable, f"{env.state_dir} доступен для записи")

    # .maind.json: валидируем через load_config (die ловим, чтобы не прерывать doctor)
    config = None
    if env.default_config.exists():
        try:
            from .config import load_config
            config, source = load_config(env)
            check(True, f".maind.json валиден (источник: {source})")
        except SystemExit:
            check(False, ".maind.json валиден", "см. ошибку валидации выше")
    else:
        legacy = env.root / ".projects.json"
        suffix = (" (есть legacy .projects.json — maind migrate from-brain)"
                  if legacy.exists() else " (создайте из .maind.example.json)")
        check(True, ".maind.json отсутствует" + suffix)

    # порты памяти — на разрешённых портах (env/конфиг), информативно
    if not quiet:
        http_port, stream_port, url = resolve_ports(env, config)
        up = health(url)
        print(f"  [info] память {url} — "
              + ("отвечает" if up else "не запущена (maind start --only memory)"))
        print(f"  [info] порты: http :{http_port}, stream :{stream_port} "
              "(override через .env AGENTMEMORY_PORT/STREAM_PORT)")

    print(f"\n{'Все проверки пройдены.' if issues == 0 else f'Проблем: {issues}'}")
    if issues:
        sys.exit(1)
