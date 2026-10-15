"""Redaction of secrets in text and documents: the values a caller knows plus the explicit formats of tokens.

``redact_text`` replaces every known value and every match of ``PATTERNS`` with a mask; ``redact_document`` does it in
the strings, the keys and the scalars of a JSON document. Only explicit token formats are patterns, so ordinary prose
is left alone. Raw streams are not redacted here: a caller decides what it keeps.
"""
import json
import os
import re

MASK = "‹redacted›"  # ‹redacted›

# Issuer formats: ``sk-`` keys, GitHub classic and fine-grained tokens, Slack tokens, AWS access key ids, an HTTP bearer
# credential. The last pattern masks the value of a ``name=value`` / ``"name": "value"`` pair whose name says secret.
_TOKENS = re.compile(r"sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"
                     r"|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|Bearer\s+\S{20,}")
_NAMED = re.compile(r"(?i)((?:api[_-]?key|token|secret|password)[\"']?\s*[=:]\s*[\"']?)[^\s\"',;]{8,}")
PATTERNS = (_TOKENS, _NAMED)

SECRET_NAME = re.compile(r"(?i)(api[_-]?key|token|secret|password)")
MIN_SECRET = 8  # a shorter value would mask ordinary words


def _values(secrets):
    found = []
    for secret in secrets or ():
        reveal = getattr(secret, "reveal", None)
        try:
            value = reveal() if callable(reveal) else secret
        except Exception:  # noqa: BLE001 — a secret that cannot be resolved now cannot be in the text either
            continue
        if isinstance(value, str) and value:
            found.append(value)
    return sorted(set(found), key=len, reverse=True)


def redact_text(text, *, secrets=(), patterns=True, mask=MASK):
    """``text`` with every known value of ``secrets`` (strings or ``Secret``) and, with ``patterns``, every explicit
    token format replaced by ``mask``. The longest value goes first."""
    for value in _values(secrets):
        text = text.replace(value, mask)
    if patterns:
        text = _TOKENS.sub(mask, text)
        text = _NAMED.sub(lambda match: match.group(1) + mask, text)
    return text


def redact_document(value, *, secrets=(), patterns=True, mask=MASK):
    """A copy of the JSON ``value`` without secrets in its strings and keys; a number or literal whose JSON text holds
    a known value becomes ``mask``."""
    known = _values(secrets)

    def walk(item):
        if isinstance(item, str):
            return redact_text(item, secrets=known, patterns=patterns, mask=mask)
        if isinstance(item, list):
            return [walk(entry) for entry in item]
        if isinstance(item, dict):
            return {redact_text(key, secrets=known, patterns=patterns, mask=mask) if isinstance(key, str) else key:
                    walk(entry) for key, entry in item.items()}
        if known and any(secret in json.dumps(item, default=str) for secret in known):
            return mask
        return item

    return walk(value)


def env_secrets(env=None):
    """The values of the variables of ``env`` (default: the process environment) whose name says api key, token,
    secret or password; values shorter than ``MIN_SECRET`` are left out."""
    source = os.environ if env is None else env
    return [value for name, value in source.items()
            if isinstance(value, str) and len(value) >= MIN_SECRET and SECRET_NAME.search(name)]
