"""HTTP-клиент на stdlib urllib (без сторонних зависимостей) — общий примитив монорепо.

Перенесён из maind.http (общение с Node-демоном agent-memory: GET/POST JSON и
healthcheck `ping`). Сетевые ошибки приводятся к понятному RuntimeError. stdlib-only."""
import json
import urllib.error
import urllib.request


def http_get_json(url: str, *, timeout: float = 5):
    """GET → распарсенный JSON. Сетевые ошибки → RuntimeError с понятным текстом."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} от {url}") from e
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"нет связи с {url}: {getattr(e, 'reason', e)}") from e


def http_post_json(url: str, payload, *, timeout: float = 10):
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


def ping(url: str, *, timeout: float = 3) -> bool:
    """True, если по url вообще отвечает HTTP (даже 4xx). HTTPError = сервис жив
    (как в brain healthcheck); URLError/OSError = недоступен."""
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False
