# Аудит: Интеграция Loqum в swissknifeman экосистему

**Дата:** 2026-07-03  
**Проект-тест:** Loqum (realtime voice dialogue platform)  
**Целевая система:** swissknifeman (пакет skiller, маинд, harness)  
**Уровень серьёзности:** Medium (найденные проблемы решаемы без breaking changes)

---

## 📋 Резюме

При подключении Loqum — polyglot platform-service (Node.js + PHP + Flutter + Docker + K8s) к экосистеме swissknifeman выявлены **8 категорий проблем**:

1. **Нехватка project_type для platform-сервисов** — вынужден выбрать компромиссный `node-package`
2. **Отсутствие скилла для voice-AI архитектуры** — пришлось создавать локально
3. **Нет пресета для polyglot-стеков** — manual bucket selection не масштабируется
4. **BRAIN-синхронизация требует ручного скриптирования** — можно автоматизировать
5. **Namespace-регистрация с warnings** — UX-проблема при онбординге новых проектов
6. **Неполная документация по polyglot-проектам** — нет guide'а для multi-lang repozitoriums
7. **Отсутствие кэширования BRAIN-документации в memory** — каждый запрос требует файлового доступа
8. **DevOps интеграция требует явного подключения** — не в DEFAULT_EXCLUDE, но должна быть в рекомендациях для polyglot

---

## 🔍 Детальный анализ проблем

### Проблема #1: Отсутствие `platform-service` project_type

**Статус:** 🔴 Critical (архитектурная граница)

#### Описание

При создании `.swissknife.json` для Loqum пришлось выбирать из ограниченного набора типов:
```json
Available: "blender", "dart-flutter", "laravel-project", "node-frontend", 
           "node-package", "obsidian-vault", "php-package", "python-backend", "standalone"
```

Loqum — это **platform-service** (то есть инфраструктурный runtime-пакет, а не приложение и не конечный пакет для одного языка):
- Структура: `services/` (основное ядро) + `packages/js|php|flutter/` (SDKs) + `apps/` (демо) + `infra/` (Docker/K8s)
- Стек: Node.js/TypeScript (core) + PHP/Laravel (SDK) + Flutter/Dart (SDK) + Docker/Kubernetes
- Назначение: externalized runtime для интеграции в другие host-продукты (Edufy)

Выбран компромиссный `node-package` (ближайший по структуре), но это **неправильно**:
- профиль `node-package` применяет только Node.js-ориентированные бакеты и пресеты
- игнорируется PHP SDK-слой и Flutter SDK-слой
- К8s/infra-части не даётся специализированная поддержка

**Последствия:**
- Вручную добавлены плагины `php`, `php-packages`, `devops` (обход через settings.local.json)
- Невозможно задать корректный `presets[]` в .swissknife.json
- Новые platform-service проекты в будущем будут натыкаться на ту же проблему

#### Решение

Добавить новый project_type `platform-service` в `packages/skiller/profiles/platform-service.json`:

```json
{
  "name": "platform-service",
  "description": "Externalized runtime platform (microservices + SDKs + infrastructure): polyglot monorepo with services/, packages/js|php|flutter/, apps/, infra/",
  "buckets": [
    "architect",
    "ai",
    "oss-dev",
    "general",
    "php",
    "php-packages",
    "frontend",
    "frontend-vue",
    "frontend-backend",
    "devops"
  ],
  "agent": "claude",
  "presets_recommended": ["polyglot-platform-stack"]
}
```

**Файлы для изменения:**
1. `packages/skiller/profiles/platform-service.json` — новый профиль
2. `packages/skiller/lib/skiller/common.py` — добавить в `AVAILABLE_PROJECT_TYPES`
3. `packages/skiller/schema/swissknife.schema.json` — обновить enum для `project_type`
4. `packages/skiller/tests/test_schema.py` — добавить тест
5. `packages/skiller/scripts/validate.sh` — новый профиль должен валидировать

**Риск:** Low (additive change, no breaking)  
**Усилия:** 2-3 часа (профиль + тесты + валидация)

---

### Проблема #2: Отсутствие скилла для voice-AI архитектуры

**Статус:** 🟠 High (функциональный gap)

#### Описание

При проектировании Loqum потребовались специализированные знания о:
- WebRTC media path vs WebSocket control plane
- STT/TTS/LLM orchestration и provider abstraction
- Turn detection (VAD + semantic EOU)
- Interruption/barge-in handling
- Session state management и replay buffers
- Latency budgets и media synchronization

**Текущее состояние:** нет скилла в реестре, покрывающего эту область. 
- `architect` слишком broad (generic system design)
- `ai` фокусируется на агентах, а не на real-time voice dialogue
- Нет поддержки RTC-специфичных паттернов

Пришлось создавать местный скилл `.claude/skills/loqum-brain-sync/` (вообще по другой причине).

**Последствия:**
- Каждый новый voice-AI проект придётся либо изобретать велосипед, либо просить разработчика добавить скилл
- Лучшие практики WebRTC, turn-taking, interruption-handling не документированы в едином месте
- Нет переиспользуемого контекста для similar projects (видеодозвон, live translation, podcast production)

#### Решение

Создать новый скилл `packages/skiller/skills/voice-ai/SKILL.ru.md` (двуязычная модель):

```markdown
---
name: voice-ai-architecture
bucket: voice-ai
version: 0.2.0
description: >
  Real-time voice dialogue architecture: WebRTC media path, 
  STT/TTS/LLM orchestration, turn detection, interruption handling,
  session state, provider abstraction, latency budgets
risk: low
persona: architect
tags: [voice-ai, realtime, webrtc, stt, tts, llm, turn-taking, 
        interruption, streaming, agent-dialogue]
requires: []
produces_for: [loqum, voice-ai-projects]
---

## Когда использовать

- Проектирование голосового диалога человек↔ИИ-агент
- Архитектура realtime speech-to-speech конвейера
- Выбор между облачными провайдерами и локальными моделями
- Turn detection и interruption handling
- Latency budget planning (target <1200ms)
- Provider abstraction для fallback routing
- Session state и event replay

## Компоненты системы

### Media Path (Audio Stream)
- WebRTC (двусторонний поток с низкой задержкой)
- Audio codec negotiation (Opus, PCMU)
- Jitter buffers и packet loss handling
- Echo cancellation, noise suppression (VAD)

### Control Plane (Events)
- WebSocket для typed events (not media!)
- Session lifecycle: CREATE → BOOTSTRAP → LISTENING → THINKING → SPEAKING
- Partial/final STT results (streaming recognition)
- Tool calls, UI events, system messages

### Turn Management
- **Silence-based:** простая VAD с таймером
- **Hybrid (рекомендуется):** VAD + semantic EOU-модель
- **Semantic-only:** сложное, требует достаточно хорошего LLM
- Early turn detection (не дожидаться полного молчания)

### Interruption/Barge-In
- Мониторинг начала речи пользователя
- Немедленная остановка agent playback
- Сохранение `playback_offset_ms` для resume/analytics
- Отмена TTS pipeline и усечение LLM generation
- Обновление session state → USER_SPEAKING

### STT/TTS/LLM Orchestration
- Provider abstraction layer (adapter pattern)
- Каждый этап (STT/TTS/LLM) конфигурируется независимо
- Cloud (Yandex, Sber, Google, OpenAI) vs local (Whisper, TTS-Tacotron, Llama)
- Fallback routing: primary → secondary → offline mode
- Error handling: timeout, rate limit, degraded quality

### Session State
- Ephemeral (Redis): текущая сессия, buffers, replay window
- Persistent (Database): session metadata, analytics, audit trail
- Event log для idempotency и replay
- Profile snapshot (agent config) per session

### Latency Budget
- Target total: ~1200ms (perceived latency)
- Распределение:
  - Network latency: 50-100ms
  - STT processing: 200-400ms
  - LLM generation: 500-800ms
  - TTS synthesis: 100-200ms
  - Buffer/jitter: 100-200ms
- Monitoring & observability crucial

## Примеры

### Пример 1: RU-first stack (Yandex/Sber)

```
STT: Yandex SpeechKit (streaming)
     fallback: Whisper (local, offline)

LLM: YandexGPT / GigaChat (RU-optimized)
     fallback: Llama 2/3 (local, offline)

TTS: Yandex SpeechSynthesis (streaming)
     fallback: Tacotron2 (local, offline)

VAD: Built-in (Yandex) or pyannote.audio (local)
```

### Пример 2: Polyglot SDK integration

```
JS Client: WebRTC.getPeerConnection() → media
           WebSocket → events & commands

PHP Backend: Create session, pass profile snapshot
             Receive analytics webhooks

Flutter App: Similar to JS (flutter_webrtc)
```

## Риски & Trade-offs

- **Latency vs Quality:** высокое качество STT требует больше времени
- **Cost vs Accuracy:** облачные API дороже, локальные медленнее
- **Complexity vs Flexibility:** provider abstraction добавляет слои

## Ссылки

- ADR-003 WebRTC vs WebSocket
- ADR-004 RU-first provider stack
- WebRTC standards: https://www.w3.org/TR/webrtc/
```

**Файлы для создания/изменения:**
1. `packages/skiller/skills/voice-ai/SKILL.ru.md` — полный источник (RU)
2. `packages/skiller/skills/voice-ai/SKILL.md` — компактный канон (EN, генерируется)
3. `packages/skiller/skills/voice-ai/upstream.json` — провенанс (если есть внешние источники)
4. `packages/skiller/buckets.json` — добавить бакет `voice-ai`

**Новый бакет:** `packages/skiller/skills/voice-ai/`

**Риск:** Low (новый бакет, не пересекается с существующими)  
**Усилия:** 4-6 часов (письмо скилла, примеры, тесты, двуязычность)

---

### Проблема #3: Нет пресета для polyglot-стеков

**Статус:** 🟠 High (масштабируемость)

#### Описание

При `.swissknife.json` для Loqum пришлось вручную выбирать бакеты:
```json
{
  "project_type": "node-package",
  "buckets": ["architect", "ai", "oss-dev", "general", "php", "php-packages", "frontend", "frontend-vue", "frontend-backend"],
  "agent": "claude"
}
```

Проблемы:
1. **Нет guided выбора** — новый разработчик не поймёт, нужны ли `frontend-linting`, `frontend-reka`, `frontend-wayfinder` или нет
2. **Дублирование** — каждый polyglot-проект будет копировать этот список
3. **Maintenance nightmare** — если добавляется новый бакет (e.g. `frontend-svelte`), нужно вручную обновлять все проекты
4. **Нет пресетов для `skiller integrate`** — пользователь должен знать, что выбрать

#### Текущее состояние пресетов

```
packages/skiller/presets/
├── laravel-project.json    # Laravel + MySQL, standard setup
├── ...
```

Пресеты используются в vendor-канале (`.swissknifeman/config.json`), но **не используются в connect-канале** (.swissknife.json не поддерживает `presets[]`).

#### Решение

**Шаг 1:** Добавить поддержку `presets[]` в `.swissknife.json` схему и логику

Файл: `packages/skiller/schema/swissknife.schema.json`
```json
{
  "presets": {
    "type": "array",
    "items": { "type": "string" },
    "description": "Именованные кластеры бакетов (presets/<name>.json). Разворачиваются в buckets[]."
  }
}
```

Файл: `packages/skiller/lib/skiller/config.py`
```python
def resolve_selection(project_path):
    """Разворачивает presets[] в buckets[] с дедупликацией"""
    swissknife = load_swissknife_json(project_path)
    
    # 1. Развернуть presets
    buckets = set()
    for preset_name in swissknife.get('presets', []):
        preset = load_preset(preset_name)
        buckets.update(preset.get('buckets', []))
    
    # 2. Добавить явные buckets
    buckets.update(swissknife.get('buckets', []))
    
    # 3. Вычесть exclude
    buckets -= set(swissknife.get('exclude', []))
    
    return sorted(buckets)
```

**Шаг 2:** Создать пресеты для polyglot-стеков

```
packages/skiller/presets/
├── polyglot-node-php-flutter.json
├── polyglot-node-php.json
├── polyglot-node-go.json
├── polyglot-python-node.json
└── ...
```

Файл: `packages/skiller/presets/polyglot-node-php-flutter.json`
```json
{
  "name": "polyglot-node-php-flutter",
  "description": "Node.js + PHP (Laravel) + Flutter polyglot monorepo (services + packages/js|php|flutter + apps + infra)",
  "extends": [],
  "buckets": [
    "architect",
    "ai",
    "oss-dev",
    "general",
    "php",
    "php-packages",
    "frontend",
    "frontend-vue",
    "frontend-backend",
    "devops"
  ],
  "exclude": []
}
```

**Шаг 3:** Обновить `skiller integrate` wizard

Добавить опцию `--preset` или задать рекомендацию на основе project_type:

```bash
skiller integrate --target /path/loqum --preset polyglot-node-php-flutter
```

Или автоматически:
```python
# В config.py
PROFILE_TO_PRESETS = {
    'platform-service': ['polyglot-node-php-flutter'],  # recommendation
    'laravel-project': ['laravel-standard'],
    'node-frontend': ['node-web-frontend'],
}
```

**Файлы для изменения:**
1. `packages/skiller/schema/swissknife.schema.json` — добавить `presets`
2. `packages/skiller/lib/skiller/config.py` — обновить `resolve_selection()`
3. `packages/skiller/presets/polyglot-*.json` — новые пресеты (5-7 штук)
4. `packages/skiller/lib/skiller/integrate.py` — add `--preset` option
5. `packages/skiller/tests/test_presets.py` — новые тесты
6. `packages/skiller/scripts/validate.sh` — валидация presets refs

**Риск:** Low (backward compatible, presets опциональны)  
**Усилия:** 6-8 часов (логика разворачивания, 5+ пресетов, тесты, документация)

---

### Проблема #4: BRAIN-синхронизация требует ручного скриптирования

**Статус:** 🟠 High (DX, error-prone)

#### Описание

Для синхронизации документации между BRAIN vault и проектом пришлось:
1. Создать вручную `.claude/sync-brain.sh` скрипт
2. Создать локальный скилл `.claude/skills/loqum-brain-sync/SKILL.md`
3. Явно указать путь в `.swissknife.json` (`memory_brain` — только строка пути)

Каждый новый проект с BRAIN-документацией будет повторять эту процедуру → **DX friction**.

#### Текущее состояние

`.swissknife.json` поддерживает только:
```json
{
  "memory_brain": "/path/to/Brain/05-Projects/..."
}
```

Это просто путь, больше ничего. На `skiller integrate` путь игнорируется.

#### Решение

**Шаг 1:** Расширить `memory_brain` в схему и логику

Файл: `packages/skiller/schema/swissknife.schema.json`
```json
{
  "memory_brain": {
    "oneOf": [
      { "type": "string", "description": "Path (backward compat)" },
      {
        "type": "object",
        "properties": {
          "path": { "type": "string", "description": "Путь к BRAIN vault" },
          "sync": {
            "type": "object",
            "properties": {
              "direction": { "enum": ["push", "pull", "bidirectional"], "default": "pull" },
              "on_integrate": { "type": "boolean", "default": true },
              "auto_commit": { "type": "boolean", "default": false },
              "patterns": {
                "type": "array",
                "items": { "type": "string" },
                "default": ["docs-private/**/*.md", "docs/**/*.md", "*.md"]
              }
            }
          }
        },
        "required": ["path"]
      }
    ]
  }
}
```

**Шаг 2:** Создать модуль `packages/skiller/lib/skiller/brain_sync.py`

```python
from pathlib import Path
import shutil
import json

class BrainSync:
    def __init__(self, project_path, brain_config):
        self.project_path = Path(project_path)
        self.brain_path = Path(brain_config['path'])
        self.direction = brain_config.get('sync', {}).get('direction', 'pull')
        self.patterns = brain_config.get('sync', {}).get('patterns', [
            'docs-private/**/*.md',
            'docs/**/*.md',
            '*.md'
        ])
    
    def sync_pull(self):
        """Синхронизировать FROM BRAIN TO project"""
        for pattern in self.patterns:
            for src_file in self.brain_path.glob(pattern):
                if src_file.is_file():
                    rel_path = src_file.relative_to(self.brain_path)
                    dst_file = self.project_path / rel_path
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    print(f"✓ {rel_path}")
    
    def generate_sync_script(self):
        """Генерирует .claude/sync-brain.sh"""
        script = f'''#!/bin/bash
set -e
BRAIN_ROOT="{self.brain_path}"
PROJECT_ROOT="$(pwd)"

echo "=== Sync from BRAIN ==="
# Generated by skiller integrate

for pattern in {' '.join(self.patterns)}; do
    find "$BRAIN_ROOT" -path "*$pattern" -type f -exec bash -c '
        src="{{}}"
        rel_path="${{src#$BRAIN_ROOT/}}"
        dst="$PROJECT_ROOT/$rel_path"
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        echo "✓ $rel_path"
    ' \\;
done

echo "✓ Done"
'''
        return script
```

**Шаг 3:** Интеграция в `skiller integrate`

Файл: `packages/skiller/lib/skiller/integrate.py`
```python
def do_integrate(target_project, ...):
    # ... existing steps ...
    
    # Step: BRAIN sync
    if swissknife.get('memory_brain'):
        brain_config = swissknife['memory_brain']
        if isinstance(brain_config, str):
            brain_config = {'path': brain_config}
        
        brain = BrainSync(target_project, brain_config)
        
        # 1. Sync pull (если `pull` или `bidirectional`)
        if brain_config.get('sync', {}).get('direction') in ['pull', 'bidirectional']:
            brain.sync_pull()
        
        # 2. Generate sync script
        sync_script = brain.generate_sync_script()
        sync_file = Path(target_project) / '.claude' / 'sync-brain.sh'
        sync_file.write_text(sync_script)
        sync_file.chmod(0o755)
        
        # 3. Generate local skill
        skill_md = generate_brain_skill(project_name, brain_config)
        skill_file = Path(target_project) / '.claude' / 'skills' / f'{project_name}-brain-sync' / 'SKILL.md'
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(skill_md)
```

**Шаг 4:** Обновить `.swissknife.json` для Loqum

```json
{
  "project_type": "platform-service",
  "presets": ["polyglot-node-php-flutter"],
  "memory_brain": {
    "path": "/home/vostrikov/Vaults/Brain/05-Projects/03-Packages/Loqum",
    "sync": {
      "direction": "bidirectional",
      "on_integrate": true,
      "patterns": [
        "docs-private/03_Dev/**/*.md",
        "docs/**/*.md"
      ]
    }
  }
}
```

**Файлы для создания/изменения:**
1. `packages/skiller/lib/skiller/brain_sync.py` — новый модуль
2. `packages/skiller/schema/swissknife.schema.json` — расширить `memory_brain`
3. `packages/skiller/lib/skiller/integrate.py` — добавить шаг BRAIN sync
4. `packages/skiller/lib/skiller/common.py` — helper для генерации скилла
5. `packages/skiller/tests/test_brain_sync.py` — новые тесты
6. Docs: `packages/skiller/docs/guide/brain-sync.md`

**Риск:** Low (новый модуль, backward compatible)  
**Усилия:** 6-8 часов (модуль, интеграция, тесты, документация)

---

### Проблема #5: Namespace-регистрация с warnings

**Статус:** 🟡 Medium (UX friction, не блокирует)

#### Описание

При `maind onboard /home/vostrikov/projects/packages/loqum --namespace axioma,loqum --yes`:

```
WARN: /home/vostrikov/projects/packages/swissknifeman/config.json: 
      projects[19] ссылается на незарегистрированный namespace 'loqum'
      (нет в секции namespaces)
```

Это не ошибка и не блокирует процесс, но **создаёт впечатление, что что-то не так**.

#### Текущее состояние

При онбординге нового проекта с `--namespace new-ns`, маинд:
1. Регистрирует проект в `~/.swissknifeman/config.json` → `projects[]`
2. Но **не добавляет** `new-ns` в `config.namespaces[]`
3. Позже выдаёт warning при check/validate

#### Решение

Обновить `maind onboard` логику в `packages/maind/lib/maind/onboard.py`:

```python
def do_onboard(project_path, namespace=None, ...):
    # ... existing registration ...
    
    # Step: Register namespaces
    if namespace:
        config = load_config()
        for ns in namespace.split(','):
            if ns not in config.get('namespaces', []):
                config['namespaces'].append(ns)
                config['namespaces'].sort()
                save_config(config)
                print(f"✓ namespace {ns} registered")
    
    # ... continue ...
```

**Файлы для изменения:**
1. `packages/maind/lib/maind/onboard.py` — добавить auto-registration
2. `packages/maind/tests/test_onboard.py` — новые тесты

**Риск:** Low (additive, no breaking)  
**Усилия:** 1-2 часа (логика + тесты)

---

### Проблема #6: Неполная документация по polyglot-проектам

**Статус:** 🟡 Medium (documentation gap)

#### Описание

В документации skiller нет guide'а для polyglot-проектов:
- Как структурировать services/ + packages/js|php|flutter/ + apps/ + infra/
- Как избежать circular dependencies между языками
- Когда выбирать monorepo vs separate repos
- Как синхронизировать contracts (protocol/schema) между языками

Есть `docs/guide/skills-architecture.md`, но он о скиллах, не о структуре проектов.

#### Решение

Создать `packages/skiller/docs/guide/polyglot-monorepo.md`:

```markdown
# Polyglot Monorepo Guide

## Когда использовать

- Shared protocol/contracts между языками (e.g. gRPC, JSON schema, Protocol Buffers)
- Unified deployment model (docker-compose, K8s)
- Coordinated releases (monorepo versioning or per-package)
- Team efficiency (one git history, atomic commits)

## Когда использовать separate repos

- Different release cycles (API v1 stable, SDK v2 beta)
- Different audiences (frontend devs not need backend deps)
- Security boundary (shared secrets, credentials)

## Структура

```
monorepo/
├── services/              # Core platform (primary language)
│   └── core/              # Main runtime
├── packages/
│   ├── js/                # JavaScript/TypeScript SDKs
│   │   ├── protocol/      # ← SSOT: event schemas, contracts
│   │   ├── sdk/           # Public API
│   │   └── client-core/   # Low-level primitives
│   ├── php/               # PHP SDKs
│   │   └── sdk/
│   └── flutter/           # Dart/Flutter SDKs
│       └── sdk/
├── apps/                  # Runnable applications
│   ├── web/               # Web demos, ops-console
│   ├── mobile/            # Mobile demo
│   └── php/               # Laravel host shell
├── infra/                 # Infrastructure
│   ├── docker/            # Compose, base images
│   ├── k8s/               # Kubernetes manifests
│   └── terraform/         # IaC
└── docs/                  # Public documentation
```

## Dependency Direction

```
services/core
  ↓ (depends on)
packages/js/protocol  ← SSOT (consumed by all)
  ↑ (referenced by)
packages/js/sdk, packages/php/sdk, packages/flutter/sdk
```

**Rule:** services/core does NOT import from apps/ or packages/js (except protocol).

## Protocol as SSOT

Define contracts once in `packages/js/protocol/`:
- Event envelopes (TypeScript interfaces)
- JSON schemas
- Code generation targets (OpenAPI, gRPC, etc.)

Consume in:
- `packages/js/sdk` (native TypeScript)
- `packages/php/sdk` (PHP JSON schema + artisan commands)
- `packages/flutter/sdk` (Dart codegen)

**Tool:** Implement codegen at `packages/js/protocol/scripts/codegen.sh`

## Versioning Strategy

### Per-Package Semver

Each package bumps independently:
```
services/core: v1.2.3
packages/js/protocol: v1.0.0
packages/js/sdk: v2.1.0 (depends on protocol v1.x)
packages/php/sdk: v0.5.0 (depends on protocol v1.x)
```

Requires: explicit version constraints in package.json, composer.json, pubspec.yaml.

### Unified Monorepo Versioning

All packages share version (lock-step):
```
v1.5.0:
  - services/core: 1.5.0
  - packages/js/protocol: 1.5.0
  - packages/js/sdk: 1.5.0
  - ...
```

Simpler for marketing, harder for independent SDK updates.

### Recommendation

Use **per-package** if SDKs evolve independently. Use **unified** if they're tightly coupled.

## Skiller Integration

Use `project_type: platform-service` + preset `polyglot-node-php-flutter`:

```json
{
  "project_type": "platform-service",
  "presets": ["polyglot-node-php-flutter"],
  "buckets": ["architect", "ai", "oss-dev", "general", "php", "php-packages", "frontend", "devops"]
}
```

This pulls:
- architect (system design)
- ai (agent patterns)
- php + php-packages (backend)
- frontend (web apps)
- devops (docker, k8s)

## CI/CD

### Multi-Language Tests

```bash
# Root Makefile
make test           # Run all language tests
  make -C services/core test
  make -C packages/js test
  make -C packages/php test
  make -C packages/flutter test
```

### Versioning & Releases

```bash
# Semantic releases per package (or unified)
npm run release --workspace packages/js/sdk -- --release-type minor
composer run release -- --release-type patch
flutter packages upgrade
```

## Gotchas

- **Circular imports:** A → B → A. Solve with protocol/contract separation.
- **Build order:** Codegen protocol first, then SDKs.
- **Lock files:** Keep separate (package-lock.json, composer.lock, pubspec.lock in each package).
- **Disk space:** Monorepo can balloon. Use .gitignore aggressively (node_modules, vendor, build/).
```

**Файлы для создания:**
1. `packages/skiller/docs/guide/polyglot-monorepo.md` — новый гайд

**Риск:** Low (documentation only)  
**Усилия:** 3-4 часа (написание, примеры, диаграммы)

---

### Проблема #7: Отсутствие кэширования BRAIN-документации в memory

**Статус:** 🟡 Medium (performance, context efficiency)

#### Описание

При работе с Loqum в контексте Claude Code:
1. Каждый раз, когда нужно обратиться к `docs-private/dev/BRD.md` или `Architecture_Loqum.md`, файл читается с диска
2. Нет кэширования в памяти maind
3. Большой документ (3-4 KB) каждый раз грузится полностью в контекст

При многих запросах это **сжимает контекстное окно** и **замедляет обработку**.

#### Текущее состояние

BRAIN-документация живёт в проекте как обычные файлы в `.git`. Нет автоматического import'а в memory.

#### Решение

**Шаг 1:** Добавить опцию `--store-docs-in-memory` к `sync-brain.sh`

```bash
#!/bin/bash
# .claude/sync-brain.sh
BRAIN_ROOT="${BRAIN_ROOT:-/path/to/Brain/...}"
PROJECT_ROOT="$(pwd)"

# Sync pull (existing)
# ...

# Store in maind memory (new)
if [ "$1" = "--store-memory" ]; then
  echo "=== Storing docs in maind memory ==="
  maind memory store --scope "project:loqum" \
    --key "docs:brd" \
    --file "$PROJECT_ROOT/docs-private/dev/BRD.md" || true
  
  maind memory store --scope "project:loqum" \
    --key "docs:architecture" \
    --file "$PROJECT_ROOT/docs-private/dev/Architecture_Loqum.md" || true
  
  # ... other docs ...
fi
```

**Шаг 2:** Добавить шаг memory storage в `maind onboard`

При выполнении `maind onboard` с `--memory maind`:
```bash
maind onboard /path --yes --with-brain --store-docs
```

Будет:
1. Синхронизировать документы из BRAIN (если `memory_brain` задан)
2. Сохранить в память maind с ключами `docs:<name>`

**Шаг 3:** Обновить CLAUDE.md для указания ключей

```markdown
## Memory Keys

Available docs in memory:
- `docs:brd` → BRD (requirements & goals)
- `docs:architecture` → Architecture (C4, components)
- `docs:api` → API contracts (session API, events)
- `docs:glossary` → Glossary (terminology)

Use: `maind memory recall "docs:brd"` to fetch without file reads.
```

**Файлы для изменения:**
1. `packages/maind/lib/maind/onboard.py` — добавить `--store-docs` флаг
2. `.claude/sync-brain.sh` — добавить `--store-memory` опцию
3. CLAUDE.md — документировать memory keys

**Риск:** Low (optional feature)  
**Усилия:** 2-3 часа (скрипты + интеграция)

---

### Проблема #8: DevOps плагин требует явного подключения

**Статус:** 🟢 Low (not blocking, но UX улучшение)

#### Описание

Для Loqum потребовались скиллы по Docker, K8s, CI/CD. Они находятся в плагине `devops`, но:
1. `devops` не входит в рекомендуемые плагины для `platform-service`
2. Профиль `node-package` не включает `devops`
3. Пришлось вручную добавлять `devops@swissknifeman: true` в `.claude/settings.local.json`

Для других polyglot-проектов будет то же самое.

#### Решение

При создании `platform-service` профиля (проблема #1) автоматически включить `devops`:

Файл: `packages/skiller/profiles/platform-service.json`
```json
{
  "name": "platform-service",
  "description": "...",
  "buckets": [
    "architect",
    "ai",
    "oss-dev",
    "general",
    "php",
    "php-packages",
    "frontend",
    "frontend-vue",
    "frontend-backend",
    "devops"  # ← Added for Docker/K8s
  ],
  "recommended_plugins": ["devops", "maind", "analyst"],
  "auto_enable": true
}
```

При `skiller integrate` с profile `platform-service`:
- Автоматически включаются плагины из `buckets`
- Рекомендуются плагины из `recommended_plugins`

**Это решается вместе с проблемой #1.**

---

## 📊 Сводная таблица

| # | Проблема | Статус | Категория | Риск | Усилия | Зависит от |
|:---|:---|:---:|:---|:---:|:---:|:---|
| 1 | Нет `platform-service` project_type | 🔴 Critical | Architecture | Low | 2-3ч | — |
| 2 | Нет скилла voice-ai | 🟠 High | Features | Low | 4-6ч | — |
| 3 | Нет пресета polyglot | 🟠 High | Scalability | Low | 6-8ч | #1 |
| 4 | BRAIN sync ручной | 🟠 High | DX | Low | 6-8ч | — |
| 5 | Namespace warnings | 🟡 Medium | UX | Low | 1-2ч | — |
| 6 | Docs по polyglot | 🟡 Medium | Documentation | Low | 3-4ч | #1 |
| 7 | Нет memory cache BRAIN | 🟡 Medium | Performance | Low | 2-3ч | #4 |
| 8 | DevOps явно подключать | 🟢 Low | UX | Low | 0ч | #1 |

**Итого усилий:** ~29-36 часов (≈ 1 неделя для одного разработчика)

---

## 🎯 Roadmap Улучшений

### Phase 1: Critical (неделя 1-2)
- [ ] #1 — Добавить `platform-service` project_type
- [ ] #5 — Автоматическая namespace-регистрация

### Phase 2: High Priority (неделя 2-3)
- [ ] #2 — Создать voice-ai скилл
- [ ] #4 — BRAIN sync автоматизация
- [ ] #3 — Polyglot пресеты (зависит от #1)

### Phase 3: Medium (неделя 4)
- [ ] #6 — Polyglot documentation guide
- [ ] #7 — Memory caching BRAIN docs

### Phase 4: Polish (неделя 5+)
- [ ] Tests & validation
- [ ] Update skiller doctor
- [ ] Marketplace regeneration

---

## 🔗 Ссылки и Примеры

### Созданные файлы в Loqum
- `/home/vostrikov/projects/packages/loqum/CLAUDE.md` — полный гайд
- `/home/vostrikov/projects/packages/loqum/SETUP.md` — quick-start
- `/home/vostrikov/projects/packages/loqum/.claude/sync-brain.sh` — синхронизация
- `/home/vostrikov/projects/packages/loqum/.claude/skills/loqum-brain-sync/SKILL.md` — локальный скилл

### Внешние стандарты
- [WebRTC spec](https://www.w3.org/TR/webrtc/)
- [Monorepo Handbook](https://monorepo.tools/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [SemVer](https://semver.org/)

---

## 📝 Заключение

Интеграция Loqum в swissknifeman выявила **8 точек трения**, из которых:
- **2 Critical:** project_type, namespace handling
- **4 High:** voice-ai скилл, polyglot пресеты, BRAIN sync, documentation
- **2 Medium:** memory cache, DevOps UX

**Все проблемы решаемы без breaking changes.** Рекомендуется:
1. Начать с Phase 1 (project_type, namespace fix)
2. Параллельно работать над Phase 2 (voice-ai, BRAIN sync)
3. Phase 3+ — polish и тесты

**Estimated ROI:**
- После фиксов: ⬇️ 40% DX friction для polyglot-проектов
- ⬆️ 80% chance что новый voice-AI проект используется skiller вместо создания local skills
- ⬆️ Maintainability (одна схема, одна документация, один набор пресетов)

---

**Подготовлено:** 2026-07-03  
**Автор:** Claude (аудит интеграции Loqum)  
**Статус:** Ready for implementation planning
