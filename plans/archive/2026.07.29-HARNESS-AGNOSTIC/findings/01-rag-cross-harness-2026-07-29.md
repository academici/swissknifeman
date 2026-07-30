# RAG-разведка: кросс-харнес факты — 2026-07-29

Слой 1 (внешнее сырьё). Прогон выполнен сессией авторинга плана (Opus 5/high) по лестнице
`context7 → perplexity-web → WebFetch first-party → GitHub API`. Дисциплина проверки
Perplexity первоисточником унаследована от `2026.07.18-FOREMAN` D19 (Perplexity-факт в
несущей позиции обязан быть подтверждён first-party).

---

## Ф1. `.agents/skills/` — фактический кросс-харнес адрес скиллов

**Вердикт:** ✅ подтверждён first-party дважды.

| Источник | Что сказано |
|:--|:--|
| `https://opencode.ai/docs/skills/` (WebFetch, 2026-07-29) | OpenCode ищет скиллы в `.opencode/skills/`, `~/.config/opencode/skills/`, **`.claude/skills/`**, `~/.claude/skills/`, **`.agents/skills/`**, `~/.agents/skills/`. Обязательные поля frontmatter — `name` (1–64, lowercase-kebab, = имя каталога), `description` (1–1024) |
| `https://cursor.com/docs/skills` (WebFetch, 2026-07-29) | Cursor ищет `.agents/skills/`, `.cursor/skills/`, `~/.agents/skills/`, `~/.cursor/skills/`; **для back-compat дополнительно** `.claude/skills/`, `.codex/skills/`. Рекурсивный обход (монорепо-дружественно). Опциональные поля: `paths` (глоб-скоуп), `disable-model-invocation`, `metadata` |

**Проекция на swissknifeman.** Пакет уже пишет `.agents/skills` как Codex-канал
(repo-grounded: `packages/skiller/lib/skiller/skillset.py:811,870,886`,
`publication.py:1239`, `doctor.py:286`). Значит текущая публикация скиллов **уже**
читается Cursor и OpenCode без единой правки — это побочный эффект Codex-канала, а не
заявленная возможность. Владелец решением 2026-07-29 объявил Cursor/OpenCode
**вне скоупа** (Claude — основной, Codex — запасной), поэтому факт фиксируется как
провенанс («не ломать `.agents/skills` — он шире, чем один Codex»), а не как задача.

## Ф2. AGENTS.md как кросс-харнес конвенция

**Вердикт:** ⚠ Perplexity-уровень, first-party не добирался (вне скоупа после решения владельца).

Perplexity (2026-07-29): AGENTS.md нативно читают Codex CLI, Cursor, Gemini CLI, OpenCode;
Claude Code центрируется на CLAUDE.md и AGENTS.md нативно не читает. Косвенное
подтверждение first-party — `wshobson/agents` `ARCHITECTURE.md` инвариант 2 (см. Ф3):
«Claude Code reads `CLAUDE.md`, a symlink to `AGENTS.md`; Codex / Cursor / OpenCode read
`AGENTS.md` natively». Для этого плана несущим является только факт «Claude Code не читает
AGENTS.md нативно» — он repo-grounded подтверждён иначе: swissknifeman ведёт ДВА носителя
(`CLAUDE.md` + `AGENTS.md`) и объявляет их разными provider-bindings одной capability
`instructions.project` (`docs/provider-support.md:340-348`).

## Ф3. `wshobson/agents` — верификация существования и архитектуры

**Вердикт:** ✅ верифицирован GitHub API + прямым чтением файла (не по памяти модели).

`GET api.github.com/repos/wshobson/agents` (2026-07-29):

```
full_name: wshobson/agents
stargazers_count: 38346
pushed_at: 2026-07-22T15:32:23Z
license: MIT
archived: false
description: Multi-harness agentic plugin marketplace for Claude Code, Codex CLI,
             Cursor, OpenCode, GitHub Copilot, and Gemini CLI
```

Корень репо: `.agents/`, `.claude-plugin/`, `.cursor-plugin/`, `.cursor/`, `.gemini/`,
`AGENTS.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `GEMINI.md`, `gemini-extension.json`,
`plugins/`, `tools/`, `docs/`, `Makefile`.

Ключевое из `raw.githubusercontent.com/wshobson/agents/main/ARCHITECTURE.md` (прочитан
целиком, 2026-07-29) — пять инвариантов:

1. **Single source of truth** — авторинг только в `plugins/<name>/`; харнес-специфичные
   артефакты генерируются адаптерами и **gitignored**. Исключение: маленькие
   native-install реестры (`.agents/plugins/marketplace.json`, `.codex-plugin/plugin.json`,
   `.cursor-plugin/`, `gemini-extension.json`) коммитятся, потому что лишь указывают на
   источник. «Never hand-edit generated files».
2. **One canonical context file** — `AGENTS.md` единственный авторский; `CLAUDE.md` —
   симлинк на него.
3. **Adapters own per-harness mechanics** — источник портируем, весь харнес-специфичный
   трансформ (переписывание frontmatter, маппинг model-alias, кап размера тела,
   переименование тулов) живёт в `tools/adapters/`; исходники не несут условной логики.
4. **Mechanical enforcement with remediation hints** — каждая находка линтера несёт
   конкретную строку-фикс.
5. **Progressive disclosure до конца** — контекст-файлы ≤ ~150 строк; тела скиллов ≤ ~8 KB.

Инструментарий: `tools/adapters/base.py` (парсер + `HarnessAdapter` ABC),
`capabilities.py` (**матрица capability, потребляется каждым адаптером**),
`codex.py`/`cursor.py`/`opencode.py`/`gemini.py`/`copilot.py`, `generate.py`,
`validate_generated.py`, `doc_gardener.py` (детект дрейфа), `tools/tests/`.
Три механических гейта: `make validate` (структурная валидация сгенерированного),
`make garden` (дрейф: мёртвые ссылки, устаревшие артефакты, oversize-скиллы,
orphan'ы marketplace), `make test` (386 тестов, включая round-trip и real-CLI smoke —
CI ставит OpenCode и Gemini и гоняет их против сгенерированного).

Model tiers: Opus (архитектура/безопасность/ревью/прод-код) · inherit (сложное, модель
выбирает пользователь) · Sonnet (доки/тесты/отладка) · Haiku (быстрые операции).
Маппинг alias → нативный ID делает адаптер на генерации (`capabilities.py:MODEL_ALIASES`).

Ссылается на first-party OpenAI **harness engineering** (`openai.com/index/harness-engineering/`)
как на источник практик и на `agents.md` как на конвенцию.

## Ф4. «8 KB — лимит тела SKILL.md у Codex» — НЕ подтверждено

**Вердикт:** ❌ утверждение в исходном виде ложно; 8 000 — бюджет ЛИСТИНГА, не тела.

`ARCHITECTURE.md` wshobson называет ~8 KB «Codex's hard limit» и режет тела скиллов под
него. Проверка по `learn.chatgpt.com/docs/build-skills` (через Perplexity с цитированием
first-party, 2026-07-29): Codex использует progressive disclosure — в контекст сначала
грузятся только `name`/`description`/`path` каждого скилла, и **этот листинг** ограничен
«максимум 2 % контекстного окна модели, либо 8 000 символов при неизвестном окне».
После выбора скилла «Codex still reads the full SKILL.md instructions for that skill».
Документированного отказа/усечения SKILL.md при превышении 8 192 байт не найдено.

**Проекция.** 37 скиллов реестра swissknifeman имеют тело > 8 KB (repo-grounded:
`find packages/skiller/skills -name SKILL.md -size +8k | wc -l` → 37; максимум —
`general/plan-protocol` 89 988 байт). По этому факту они **не сломаны на Codex**.
Реальный дефицит другой и он про листинг: качество `description` и число
одновременно установленных скиллов определяют, попадёт ли скилл в бюджет обнаружения.
Кап тела 8 KB в стиле wshobson — перестраховка, а не требование платформы;
принимать его как правило нельзя без собственного замера.

## Ф5. Состояние provider-контракта swissknifeman (repo-grounded, не RAG)

Приведено здесь, потому что все внешние сравнения выше опираются на этот срез.
Источник — `docs/provider-support.md` (генерируется `scripts/provider-docs.py --write`
из `configs/provider-capabilities.json`), прочитан целиком 2026-07-29.

- Contract `1.0.0`, Catalog `1.0.0`, 35 common capabilities, Native Extensions — 0.
- Провайдеров два: `claude-code`, `codex`.
- Уровни: `native` / `adapted` / `unsupported`; каждая запись несёт binding, adapter,
  diagnostic, limitations и evidence со ссылкой на артефакт закрытой фазы.
- Precedence выбора провайдера заморожен: `operation > project > fleet-project >
  fleet-defaults > legacy`.
- **Codex `unsupported` в 15 capability из 35**: `agent-packs.lifecycle`,
  `analytics.legacy-migration`, `context.output-style`, `context.plans-directory`,
  `lifecycle.changelog-gate`, `lifecycle.command-log`, `lifecycle.memory`,
  `lifecycle.notification`, `lifecycle.pack-guard`, `lifecycle.review-gate`,
  `lifecycle.router`, `lifecycle.run-report`, `security.safe-dirs`, `settings.audit`,
  `workflows.status`.
- **Claude Code `unsupported` в 3**: `context.observer` (у Codex — native),
  `lifecycle.daemon-safety`, `lifecycle.git-guardrails` (последние две — `unsupported`
  у обоих, то есть объявленная, но нереализованная интенция).
- Диагностика отказа единая: `HARNESS_ACTIVATION_UNSUPPORTED`, fail-closed.

## Ф6. Прочие repo-grounded замеры этой сессии

| Замер | Команда | Результат |
|:--|:--|:--|
| Размер корневых инструкций | `wc -l CLAUDE.md AGENTS.md` | CLAUDE.md **194** строки / 20 705 байт; AGENTS.md **96** строк / 7 501 байт |
| Число бакетов скиллов | `ls packages/skiller/skills/` | 48 бакетов (в т.ч. `laravel-*` ×7, `frontend-*` ×12) |
| Зрелость agent-packs | `cat …/agent-packs/backend-laravel/pack.json` | pack `backend-laravel` **v0.12.2**: semver, 20 вопросов интервью, 19 файлов рендера, `requires.skills` ×11, model-тиры `MODEL_REVIEWER=opus` / `MODEL_SLICE_BUILDER=sonnet` / `MODEL_RECON=haiku` |
| Набор паков | `ls …/agent-packs/` | `_common`, `backend-laravel`, `dart-flutter`, `laravel-package`, `node-frontend`, `python-backend`, `role-cto`, `role-founder`, `role-maintainer`, `role-tech-lead` + `role-bindings.json` |
| Возраст framework-доков | `packages/skiller/docs/agent-framework/framework-overview.md` | версия каркаса объявлена **`v0.1.0-wip` (2026-06-23)**, agent-packs и lock помечены `🔜 в работе` — при живом паке v0.12.2 и работающем `.claude/agent-pack.lock.json` |

## Не проверено (риск принят явно)

- `[UNVERIFIED]` Реальное поведение Codex CLI при установке скилла > 8 KB — замера на
  живом CLI не делалось, вывод Ф4 стоит на доке.
- `[UNVERIFIED]` Утверждение Ф2 о нативной поддержке AGENTS.md у Cursor/Gemini/OpenCode —
  first-party не добиралось; вне скоупа плана по решению владельца.
- `[UNVERIFIED]` Средний размер плагина у wshobson («5.5 компонентов», из исходного
  аудита) — в `ARCHITECTURE.md` числа нет, отдельно не считалось.
