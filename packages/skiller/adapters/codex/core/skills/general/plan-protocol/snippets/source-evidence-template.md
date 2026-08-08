# Шаблон evidence bundle — `committed-bundle`-тир (P2.7)

Исполнимая форма bundle-требований (SSOT формулировок — `plan-portability-v1.md`
§Bundle requirements плана `2026.07.24-AGENT-RELIABILITY`; здесь — ЦИТАТА и структура,
не переписывание). Нужен КАЖДОМУ item'у, чей `portability.tier == "committed-bundle"`
(multi-session/high-risk/handoff/audit-работа, D26) и который несёт committed evidence
input сверх обычных `Files`/`Required Reads`.

## Раскладка bundle-каталога

```
plans/<PLAN-ID>/artifacts/<Pn.m>/evidence/
├── manifest.json     # обязателен — точный список членов bundle'а
├── verify.py          # обязателен — верификатор (существование проверяется, не исполняется предикатом)
└── <файлы>            # минимизированный набор, ровно то, что перечислено в manifest.json
```

## `manifest.json` — обязательные поля

```json
{
  "bundle_id": "<Pn.m>-<slug>",
  "files": [
    "<bundle-relative path 1>",
    "<bundle-relative path 2>"
  ],
  "privacy": {
    "minimized": true,
    "excluded_classes": ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]
  },
  "producer": "<команда/скрипт, которым bundle получен — детерминированно, без часов/случайности/сети>"
}
```

- `files` — ТОЧНЫЙ список members bundle'а (relative к каталогу bundle'а); `manifest.json`
  и `verify.py` сами в этот список НЕ входят (исключены из сверки `task_contract.bundle_lint`).
- `privacy.minimized` — `true`, только если bundle несёт РОВНО то, что было фактически
  прочитано для execution input; `excluded_classes` называет, что осознанно оставлено ЗА
  бортом (не «ничего», а именно перечень: `raw-transcript-bodies` / `chain-of-thought` /
  `tool-payloads` / `secrets` — из тех, что реально могли бы попасть).
- `producer` — команда, которой bundle воспроизводим (детерминированно, тем же прогоном
  на том же дереве, без часов/случайности/сети — иначе `content_hash`/manifest не
  воспроизводится независимым аудитором, ровно дефект F3/F4 аудита P2).

## Команда верификации

```bash
PYTHONPATH="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/lib" python3 -c '
from task.task_contract import bundle_lint
code = bundle_lint(
    "plans/<PLAN-ID>/artifacts/<Pn.m>/evidence",
    manifest_path="plans/<PLAN-ID>/artifacts/<Pn.m>/evidence/manifest.json",
    verifier_path="plans/<PLAN-ID>/artifacts/<Pn.m>/evidence/verify.py",
    declared_privacy={"minimized": True, "excluded_classes": ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]},
)
print(code or "allow")
'
```

Зелёное — `allow`. Отказ — `BUNDLE_ARTIFACT_MISSING` (manifest/verifier не найдены на
диске) либо `BUNDLE_PRIVACY_MISMATCH` (фактический набор файлов ≠ `manifest.json::files`,
ИЛИ сигнатурный скан байтов нашёл класс содержимого, перечисленный в
`declared_privacy.excluded_classes` как исключённый, — `bundle_lint` ВЫЧИСЛЯЕТ это по
фактическим байтам, а не читает декларацию как данность, D23/F2/F4). Оба кода — реальные,
не структурные: чинится САМИМ bundle'ом (убрать лишнее/добавить недостающее в manifest),
не ослаблением проверки.

## Запрещённые классы содержимого (перечень, не пример)

- **Сырые тела транскриптов** (`raw-transcript-bodies`) — полные диалоги/логи агента как
  есть; вместо них — извлечённый факт со ссылкой на источник.
- **Chain-of-thought** — промежуточные рассуждения модели; вместо них — итоговое решение
  и его обоснование в 1–3 строки.
- **Tool-payloads** — сырые ответы инструментов (полные JSON API-вызовов и т.п.); вместо
  них — извлечённое значение.
- **Секреты** — токены/пароли/ключи/PII в любой форме, даже тестовые/примерные, похожие
  на реальные по сигнатуре.

## Полное замыкание зависимостей

Если файл bundle'а ссылается на артефакт вне bundle'а (другой путь, другой bundle) —
референс ЛИБО приносится внутрь bundle'а (замыкание полное), ЛИБО bundle не самодостаточен
и холодная сессия падает на втором файле (`plan-portability-v1.md` §Bundle requirements).

## Один нейтральный semantic carrier

`portability.semantic_carrier` + `provider_renderers` — bundle несёт ОДНУ нейтральную
форму; Claude/Codex-рендеры — проекции, никогда не источник истины
(`task-contract-v1.md:187-200`, `context`-значения — та же таблица, что
`snippets/launch-block-template.md`).
