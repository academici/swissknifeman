---
name: model-verification
bucket: blender-modeling
version: 0.1.0
description: "Полная проверка параметрических Blender-моделей: provenance, config, inventory, evaluated mesh, интерфейсы, визуальные доказательства, restore и report. Использовать при подготовке release/export, аудите каждой печатной детали и сопряжения либо после изменения geometry/config."
risk: write
persona: oss-dev
tags: [blender, cad, verification, evidence, release, fdm, sla]
requires: [mcp-blender, model-rules, parametric-config]
produces_for: [build-loop]
outputs: ["models/{model}/test/artifacts/verification/current/"]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Проверка модели

Проверяй полную модель через единый переносимый lifecycle и одну модельную
инструкцию. Оставляй общими механики capture; инвентарь, интерфейсы, ракурсы,
ожидаемые наблюдения, пороги, printer-факты и blockers держи в модели.

## Загрузи контракт модели

1. Прочитай активную модель и режим через поддерживаемый проектом env-loader.
2. Прочитай правила модели, конфигурацию и модельную verification-инструкцию.
3. Проверь, что инструкция заполняет поля из
   [references/model-local-template.md](references/model-local-template.md).
4. Остановись, если нет авторитетного источника inventory или interfaces. Не
   восстанавливай product truth из capture-скрипта или другой модели.

## Объяви класс прогона

- Используй `release` для кандидата, который может стать GREEN.
- Используй `diagnostic` только при явно запрошенном продолжении после известного
  или обнаруженного RED.
- Маркируй каждый диагностический output как `diagnostic-red`; никогда не promote его.
- Сохраняй для грязных кандидатов метку `candidate-uncommitted`; не называй их
  committed release.

## Исполни упорядоченный lifecycle

Не меняй порядок и не подменяй ранние гейты поздними доказательствами.

1. **Provenance/preflight:** разреши и запинь project root, отклони foreign imports,
   запиши model/mode/tool versions/source state и хэши configuration, builders,
   inventory, local instruction, runner, shared skill/template и все остальные declared inputs.
2. **Plain-Python gates:** до capture выполни проверки configuration, derivation,
   inventory schema и cross-part.
3. **Default production build:** собери модель штатным entry point в полном/default
   режиме и сравни точный owned final universe с модельным inventory.
4. **Evaluated mesh и interfaces:** измерь каждую финальную печатную деталь и каждый
   реальный interface в evaluated world space с config-owned tolerances. Отклоняй
   bbox-only fit claims и непроверенные mirror/sibling детали.
5. **Изолированные ракурсы:** сними читаемые primary и oblique technical views каждой
   финальной детали; добавь detail/underside/interface views из модельной инструкции.
6. **Assembly contexts:** показывай только target и реальные counterparts в заданном
   tech/xray/section view. Считай cut/section только дополнительным display evidence,
   не доказательством topology, diameter, interface или export.
7. **Expected-vs-observed analysis:** открой каждое обязательное изображение и запиши
   falsifiable metric-linked observation. Missing, stale, edge-on, occluded, unreadable
   или ambiguous evidence даёт RED; screenshot не может auto-pass сам себя.
8. **Report и restore:** выдай одну evidence-linked строку на каждый required step,
   сохрани owner gates и physical non-claims, восстанови scene/viewport в `finally` и
   проверь restore до вычисления aggregate verdict.

Останавливай release до дорогого capture, если provenance, plain-Python, inventory или
evaluated-mesh gate красный. Явно запрошенный diagnostic может продолжить сбор evidence,
но его aggregate остаётся RED.

## Защити состояние доказательств

- Пиши routine evidence только в точный модельный
  `test/artifacts/verification/current/`.
- Разреши path, отклони symlink и escape, удаляй только проверенный `current/`.
  Никогда не удаляй parent, glob, unresolved variable или данные другой модели.
- Сразу после пересоздания пиши open manifest. Записывай hashes, versions, run class,
  actual build mode, required ids, candidate state, artifact paths и restore result.
- Считай evidence stale при изменении любого относящегося к нему source hash, tool
  version, mode, scale, profile или local contract input.
- До report closure или promotion заново проверь каждые required step id, artifact path,
  artifact hash, coverage row, source hash и restore result по open manifest.
- Делай promotion только отдельной явной командой в новый baseline id. Отклоняй
  diagnostic, stale, incomplete, restoration-failed и non-GREEN runs.

## Сохрани транзакционные границы

До capture сохрани object/collection visibility, selection, active object, scene,
camera, каждый затрагиваемый viewport, projection, lens/clipping, shading, overlays,
xray и local-view state. Изолируй только объявленный context. Удали временные
measurement datablocks и восстанови saved state в `finally`. Неполный restore даёт
aggregate RED.

## Вычисли verdict

Используй per-step `GREEN`, `RED`, `BLOCKED` или `NOT_RUN`. Aggregate GREEN требует,
чтобы каждый required step был GREEN, evidence было fresh, coverage — exact, restore —
проверен, а owner gate не был выдан за verified. Оставляй physical fit, strength,
material behaviour, optical performance и print qualification непроверенными до прямого
доказательства.

## Связанные скиллы

- `blender-modeling/build-loop` — инкрементальная работа с деталями и вход в whole-model checks.
- `blender-modeling/model-rules` — модельные construction и camera conventions.
- `blender-modeling/parametric-config` — configuration, derivation и plain-Python gates.
- `blender/mcp-blender` — Blender execution, viewport, camera и geometry inspection tools.
