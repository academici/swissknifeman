# Research: Loqum Integration Audit — Quick Summary

**Дата:** 2026-07-03  
**Полный отчёт:** [`AUDIT-loqum-integration.md`](../AUDIT-loqum-integration.md)

---

## 🎯 TL;DR

При интеграции **Loqum** (voice-AI platform, polyglot monorepo: Node.js + PHP + Flutter + Docker/K8s) в swissknifeman выявлены **8 проблем**:

| # | Проблема | Severity | Quick Fix |
|:---|:---|:---:|:---|
| 1️⃣ | Нет `platform-service` project_type | 🔴 Critical | Добавить профиль (2-3ч) |
| 2️⃣ | Нет voice-ai скилла | 🟠 High | Создать скилл (4-6ч) |
| 3️⃣ | Нет polyglot пресета | 🟠 High | Добавить preset (6-8ч) |
| 4️⃣ | BRAIN sync требует скрипта | 🟠 High | Автоматизировать (6-8ч) |
| 5️⃣ | Namespace warnings на onboard | 🟡 Medium | Auto-register (1-2ч) |
| 6️⃣ | Нет docs по polyglot | 🟡 Medium | Написать guide (3-4ч) |
| 7️⃣ | Нет memory cache для BRAIN | 🟡 Medium | Добавить caching (2-3ч) |
| 8️⃣ | DevOps не в defaults | 🟢 Low | Включить в preset (0ч) |

**Всего:** ~29-36 часов (1 неделя) · Риск: Low · Breaking: No

---

## 🚨 Critical Issues

### #1: Нет `platform-service` project_type

**Проблема:** Loqum — externalized runtime с `services/core/` (основное ядро), `packages/js|php|flutter/` (SDKs), `apps/` (demos), `infra/` (Docker/K8s). Но project_type ограничен:
```
node-package, php-package, laravel-project, node-frontend, 
python-backend, blender, dart-flutter, obsidian-vault, standalone
```

Пришлось выбрать компромиссный `node-package` → не включились PHP/Flutter/DevOps бакеты.

**Решение:**
```json
// packages/skiller/profiles/platform-service.json
{
  "name": "platform-service",
  "buckets": ["architect", "ai", "oss-dev", "general", "php", "php-packages", 
              "frontend", "frontend-vue", "frontend-backend", "devops"]
}
```

**Файлы:** `profiles/platform-service.json`, `common.py` (enum), `schema/swissknife.schema.json` (enum)  
**Тесты:** `tests/test_schema.py`

---

### #5: Namespace warnings при onboard

**Проблема:**
```bash
maind onboard ... --namespace axioma,loqum --yes
# WARN: projects[19] ссылается на незарегистрированный namespace 'loqum'
```

**Решение:** В `packages/maind/lib/maind/onboard.py`:
```python
def do_onboard(...):
    # Register namespaces in config
    if namespace:
        config = load_config()
        for ns in namespace.split(','):
            if ns not in config.get('namespaces', []):
                config['namespaces'].append(ns)
                save_config(config)
```

---

## 🎨 High Priority

### #2: Нет voice-ai-architecture скилла

**Проблема:** Нет документированного скилла для:
- WebRTC media path vs WebSocket control plane
- STT/TTS/LLM orchestration & provider abstraction
- Turn detection (VAD + semantic EOU)
- Interruption/barge-in handling
- Latency budgets & session state

**Решение:** Создать `packages/skiller/skills/voice-ai/SKILL.ru.md` (двуязычная модель):
- ✅ SKILL.ru.md (полный русский источник, правит человек)
- 🤖 SKILL.md (компактный EN, генерируется из RU)
- Примеры: Yandex/Sber stack, WebRTC patterns
- Ссылки: ADR-003, ADR-004

**Бакет:** `voice-ai`

---

### #3: Нет polyglot-стека пресета

**Проблема:** Loqum требует вручную собирать бакеты. Каждый новый polyglot-проект будет повторять.

**Решение:**
```bash
# Расширить schema: .swissknife.json поддерживает presets[]
{
  "presets": ["polyglot-node-php-flutter"],
  "buckets": [...optional overrides...]
}
```

Создать пресеты:
- `polyglot-node-php-flutter.json`
- `polyglot-node-php.json`
- `polyglot-node-go.json`
- `polyglot-python-node.json`

**Logic в `config.py`:** развернуть `presets[]` → `buckets[]` с дедупликацией.

---

### #4: BRAIN-синхронизация требует ручного скриптирования

**Проблема:** Для синхронизации документации пришлось:
1. Создать вручную `.claude/sync-brain.sh`
2. Создать локальный скилл
3. Явно указать path в `.swissknife.json`

**Решение:** Расширить `.swissknife.json`:
```json
{
  "memory_brain": {
    "path": "/home/vostrikov/Vaults/Brain/05-Projects/03-Packages/Loqum",
    "sync": {
      "direction": "bidirectional",
      "on_integrate": true,
      "patterns": ["docs-private/**/*.md", "docs/**/*.md"]
    }
  }
}
```

Новый модуль `packages/skiller/lib/skiller/brain_sync.py`:
- `BrainSync.sync_pull()` — скопировать из BRAIN в проект
- `BrainSync.generate_sync_script()` — генерить `.claude/sync-brain.sh`
- Интеграция в `integrate.py` — шаг BRAIN sync на `skiller integrate`

---

## 📖 Medium Priority

### #6: Нет документации по polyglot

**Проблема:** Нет guide'а для:
- Структуры services/ + packages/js|php|flutter/ + apps/ + infra/
- Dependency direction (services → packages → apps)
- Protocol as SSOT (contracts once, consume in all SDKs)
- Versioning: per-package vs unified
- CI/CD: multi-language test matrix

**Решение:** `packages/skiller/docs/guide/polyglot-monorepo.md`

---

### #7: Нет memory cache BRAIN-документации

**Проблема:** Каждый запрос читает файлы с диска. Большие документы сжимают контекст.

**Решение:** Расширить `sync-brain.sh` опцией `--store-memory`:
```bash
bash .claude/sync-brain.sh --store-memory
# maind memory store --scope project:loqum --key "docs:brd" --file ...
```

Обновить CLAUDE.md с memory keys.

---

## ✅ Низкоприоритетные

### #8: DevOps не в defaults

**Решается вместе с #1:** профиль `platform-service` включает `devops` в buckets.

---

## 📊 Implementation Roadmap

```
Week 1 (Phase 1: Critical)
  ├─ #1 platform-service profile + schema
  └─ #5 namespace auto-register

Week 2 (Phase 2: High)
  ├─ #2 voice-ai skill (RU/EN)
  ├─ #4 brain_sync.py module
  └─ #3 polyglot presets (depends on #1)

Week 3 (Phase 3: Medium)
  ├─ #6 polyglot-monorepo.md guide
  └─ #7 memory caching

Week 4 (Phase 4: Polish)
  ├─ Tests & validate
  ├─ skiller doctor update
  └─ marketplace regeneration
```

---

## 🔗 Файлы в этом аудите

| Файл | Что содержит |
|:---|:---|
| `AUDIT-loqum-integration.md` (полный) | 8 проблем с кодом, примерами, риском |
| Этот файл | Краткая справка (TL;DR) |

---

## 💡 Как использовать этот аудит

1. **Для планирования:** скопировать Roadmap в issue tracker
2. **Для PR'ов:** каждый issue → свой PR (Phase 1, затем Phase 2, etc.)
3. **Для тестов:** в каждом PR добавить `tests/test_*.py`
4. **Для docs:** обновить `packages/skiller/docs/guide/` при добавлении скилла/пресета

---

**Статус:** Ready for implementation  
**Контакт:** Аудит проведён при интеграции Loqum в swissknifeman
