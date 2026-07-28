"""HTTP-клиент на stdlib urllib (без сторонних зависимостей) — общий примитив монорепо.

Перенесён из maind.http (общение с Node-демоном agent-memory: GET/POST JSON и
healthcheck `ping`). Сетевые ошибки приводятся к понятному RuntimeError. stdlib-only."""
import json
import urllib.error
import urllib.request


class HTTPUnauthorizedError(RuntimeError):
    """HTTP 401 — сервер ЖИВ, но запрос не авторизован (bearer отсутствует/неверен).
    Подкласс RuntimeError: существующие `except RuntimeError` продолжают ловить и её,
    вызывающий код, которому важно различие, ловит её отдельно ПЕРЕД RuntimeError."""


def _request(url, *, method, data=None, headers=None, timeout):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HTTPUnauthorizedError(f"HTTP 401 от {url}") from e
        raise RuntimeError(f"HTTP {e.code} от {url}") from e
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"нет связи с {url}: {getattr(e, 'reason', e)}") from e


def http_get_json(url: str, *, timeout: float = 5, headers=None):
    """GET → распарсенный JSON. Сетевые ошибки → RuntimeError; 401 → HTTPUnauthorizedError.
    `headers` — опционально (напр. bearer-токен); без него поведение прежнее."""
    body = _request(url, method="GET", headers=headers, timeout=timeout)
    return json.loads(body or "null")


def http_post_json(url: str, payload, *, timeout: float = 10, headers=None):
    """POST JSON → распарсенный JSON-ответ (пустой ответ → {}). `headers` — опционально,
    сливается поверх дефолтного Content-Type; без него поведение прежнее."""
    data = json.dumps(payload).encode("utf-8")
    merged = {"Content-Type": "application/json", **(headers or {})}
    body = _request(url, method="POST", data=data, headers=merged, timeout=timeout)
    return json.loads(body) if body.strip() else {}


def ping(url: str, *, timeout: float = 3, headers=None) -> bool:
    """True, если по url вообще отвечает HTTP (даже 4xx/401). HTTPError = сервис жив
    (как в brain healthcheck); URLError/OSError = недоступен. `headers` — опционально,
    без него поведение прежнее (истину про авторизацию ping не даёт — см. HTTPUnauthorizedError
    у http_get_json/http_post_json для протектед-эндпоинтов)."""
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="GET", headers=headers or {}),
                               timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False
