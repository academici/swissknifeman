"""Текстовые помощники — дословный общий код."""
import re

SLUG_RE = re.compile(r"[^a-z0-9-]")


def sanitize(name):
    """Slug: lower, пробелы/подчёркивания → дефис, прочее убрать, схлопнуть дефисы."""
    name = name.lower().replace(" ", "-").replace("_", "-")
    name = SLUG_RE.sub("", name)
    return re.sub(r"-{2,}", "-", name).strip("-")


def parse_frontmatter(text):
    """Разбор первого `---`-блока YAML-frontmatter — superset всех потребителей.

    Единый источник истины парсинга для skiller/harness/maind (раньше — четыре
    разошедшиеся копии). Возвращает dict:
      • скаляр               → str (обрамляющие кавычки сняты);
      • блок-скаляр `|`/`>`  (+ опц. чомп/индент `|-`, `>+`, `>2`…) → склеенная строка
        (`|` — с переносами, `>` — через пробел; иначе `description: |` молча терялся бы);
      • inline-список `[a,b]` → list;
      • многострочный список `- item` под ключом с пустым значением → list.
    Ключ с пустым значением БЕЗ последующих `- item` остаётся пустой строкой
    (совместимость со skiller, где пустой скаляр ожидается строкой). Тело после
    закрывающего `---` игнорируется. BOM/CRLF нормализуются. stdlib-only, без pyyaml.

    Принимает ТЕКСТ (не путь): решение о кодировке (utf-8 vs utf-8-sig) — за вызывающим.
    """
    if text.startswith("\ufeff"):  # срезаем BOM, если пришёл в utf-8 без -sig
        text = text[1:]
    lines = text.replace("\r\n", "\n").splitlines()
    fm = {}
    if not lines or lines[0].strip() != "---":
        return fm
    i, cur = 1, None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        # продолжение многострочного списка `- item` под текущим ключом
        if cur is not None and line[:1] in (" ", "\t") and line.strip().startswith("-"):
            if not isinstance(fm.get(cur), list):
                fm[cur] = []  # первый `- item` превращает пустой скаляр в список
            fm[cur].append(line.strip()[1:].strip().strip('"').strip("'"))
            i += 1
            continue
        cur = None
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            # блок-скаляр только если value — РОВНО заголовок |/> (+ опц. чомп/индент),
            # а не описание, начинающееся с этих символов ("description: > см." — скаляр).
            if value[:1] in ("|", ">") and all(c in "+-0123456789" for c in value[1:]):
                block, i = _collect_block_scalar(lines, i + 1)
                fm[key] = (" " if value[0] == ">" else "\n").join(block)
                continue
            if value.startswith("[") and value.endswith("]"):
                fm[key] = [x.strip().strip('"').strip("'")
                           for x in value[1:-1].split(",") if x.strip()]
            elif value == "":
                fm[key] = ""  # скаляр по умолчанию; станет списком при первом `- item`
                cur = key
            else:
                fm[key] = value.strip('"').strip("'")
        i += 1
    return fm


def _collect_block_scalar(lines, start):
    """Собрать отступные строки YAML-блок-скаляра начиная с lines[start].
    Возвращает (строки без общего отступа, индекс первой неотступной строки).
    Пустые строки сохраняются как переносы; хвостовые — обрезаются (clip-чомп)."""
    block = []
    i = start
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "---":
            break
        if ln.strip() == "":
            block.append("")
        elif ln.startswith((" ", "\t")):
            block.append(ln.strip())
        else:
            break
        i += 1
    while block and block[-1] == "":
        block.pop()
    return block, i


def parse_inline_list(value):
    """Нормализовать значение frontmatter к списку строк.

    Терпит как уже-разобранный list (parse_frontmatter вернул список для `[a,b]`
    или `- item`), так и сырую inline-строку `[a, b]` (когда значение осталось
    строкой). Всё прочее → []. Обрамляющие кавычки снимаются, пустые отбрасываются."""
    if isinstance(value, list):
        return [str(i).strip().strip('"').strip("'")
                for i in value if str(i).strip()]
    value = (value or "").strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
    return [i for i in items if i]
