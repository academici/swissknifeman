"""Signed built-in webhook EventSink. Secrets arrive resolved by the relay consumer."""

from __future__ import annotations

import http.client
import json
import socket
import ssl
from collections.abc import Mapping
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any

from skm.kernel.clock import Clock
from skm.kernel.events import EventEnvelope
from skm.kernel.json_types import JsonValue
from skm.modules.integrations.domain.reports import DeliveryResult
from skm.modules.integrations.generated.settings import HooksWebhookSettings
from skm.platform.jsonc.canonical import format_timestamp

from ._pinned_http import HttpRefused, PinnedHttpClient
from .webhook_signing import sign

__all__ = ["WebhookSink"]

_RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})


class WebhookSink:
    sink_id = "webhook"

    def __init__(
        self,
        *,
        http: PinnedHttpClient,
        settings: HooksWebhookSettings | Mapping[str, Any],
        clock: Clock,
        version: str,
    ) -> None:
        self._http, self._settings, self._clock, self._version = http, settings, clock, version

    def config_schema(self) -> str:
        return "urn:skm:integrations:defs:v1#/$defs/webhook_target"

    def deliver(self, envelope: EventEnvelope, config: Mapping[str, JsonValue]) -> DeliveryResult:
        target = dict(config)
        now = self._clock.now()
        document = {
            "schema": "urn:skm:integrations:webhook-delivery:v1",
            "delivery_id": config["delivery_id"],
            "subscription_id": config["subscription_id"],
            "attempt": config["attempt"],
            "sent_at": format_timestamp(now),
            "event": envelope.to_json(),
        }
        # Event payloads admit finite JSON numbers; preserve their wire representation.
        body = json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        keys = [str(config["secret"])]
        previous = target.get("previous_secret")
        if previous is not None:
            keys.append(str(previous))
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": f"skm-webhook/{self._version}",
            "SKM-Event-Id": str(envelope.id),
            "SKM-Event-Type": envelope.type,
            "SKM-Delivery-Id": str(config["delivery_id"]),
            "SKM-Subscription-Id": str(config["subscription_id"]),
            "SKM-Attempt": str(config["attempt"]),
            "SKM-Signature": sign(body, secrets=keys, timestamp=int(now.timestamp())),
        }
        custom = target.get("headers", {})
        if isinstance(custom, dict):
            for name, value in custom.items():
                if name.lower() in {"authorization", "host"} or name.lower().startswith(("skm-", "content-")):
                    return DeliveryResult(False, False, "headers_refused", None, None, None)
                headers[name] = str(value)

        def setting(name: str, default: object) -> Any:
            policy = target.get("_webhook_policy")
            if isinstance(policy, dict) and policy.get(name) is not None:
                return policy[name]
            if isinstance(self._settings, Mapping):
                return self._settings.get(name, default)
            return getattr(self._settings, name, default)

        try:
            response = self._http.post(
                str(config["url"]),
                body=body,
                headers=headers,
                timeout_ms=int(str(config["timeout_ms"])),
                allow_private_networks=bool(setting("allow_private_networks", False)),
                allow_http_loopback=bool(setting("allow_http_loopback", False)),
                max_response_bytes=int(setting("max_response_bytes", 65536)),
            )
        except HttpRefused as exc:
            return DeliveryResult(False, False, str(exc), None, None, None)
        except ssl.SSLError:
            return DeliveryResult(False, False, "tls", None, None, None)
        except TimeoutError:
            return DeliveryResult(False, True, "timeout", None, None, None)
        except socket.gaierror:
            return DeliveryResult(False, True, "dns", None, None, None)
        except (OSError, http.client.HTTPException):
            return DeliveryResult(False, True, "network", None, None, None)
        except ValueError:
            return DeliveryResult(False, False, "request_invalid", None, None, None)
        status = response.status
        ok, retry = 200 <= status < 300, status in _RETRYABLE
        reason = (
            None
            if ok
            else "redirect_refused"
            if 300 <= status < 400
            else "gone"
            if status == 410
            else f"http_{status}"
        )
        delay = None
        if retry and response.retry_after:
            try:
                delay = max(0, int(response.retry_after) * 1000)
            except ValueError:
                try:
                    date = parsedate_to_datetime(response.retry_after)
                    delay = max(0, int((date.astimezone(UTC) - now).total_seconds() * 1000))
                except (ValueError, TypeError, OverflowError):
                    pass
        return DeliveryResult(
            ok, retry, reason, status, delay, response.body[:2048].decode("utf-8", "replace")
        )
