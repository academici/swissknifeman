"""Управляемый markdown-блок: идемпотентная вставка/обновление с маркерами и хэшем.

Общий примитив монорепо (перенесён из maind.blocks, где был единственный писатель
таких блоков в CLAUDE.md/.ai целевых проектов). Чужой текст не трогается, дрейф
детектится по короткому хэшу содержимого. stdlib-only."""
import hashlib
import re


def content_hash(text: str) -> str:
    """Короткий стабильный хэш содержимого (для детекта дрейфа управляемых артефактов)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def managed_block(content: str, marker: str, *, owner: str = "maind") -> str:
    """Управляемый блок с маркерами begin/end и хэшем: `owner` — единственный его писатель."""
    h = content_hash(content)
    return (f"<!-- {marker} hash={h} (managed by {owner} — не редактировать вручную) -->\n"
            f"{content.rstrip()}\n<!-- /{marker} -->")


def upsert_block(text: str, content: str, marker: str,
                 *, owner: str = "maind") -> "tuple[str, bool, str]":
    """Вставить/обновить управляемый блок в text. Возвращает (new_text, changed, state),
    state ∈ {absent→install, stale→update, fresh→skip}. Существующий блок ищется по маркерам,
    чужой текст не трогается; отсутствует — добавляется в конец."""
    block = managed_block(content, marker, owner=owner)
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
