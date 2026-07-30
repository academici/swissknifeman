# RAG-разведка: как два провайдера грузят инструкции — 2026-07-29

Слой 1 (внешнее сырьё). Прогон выполнен заходом `plan-design ... P1` (Opus 5/high) по
лестнице `perplexity-web → first-party`. Дисциплина унаследована от `2026.07.18-FOREMAN`
D19: Perplexity-факт в несущей позиции подтверждается первоисточником. Оба факт-класса
ниже несущие для фазы P1 — они определяют, что вообще может быть носителем правила у
каждого провайдера.

---

## Ф7. Claude Code — модель загрузки инструкций

**Вердикт:** ✅ подтверждён first-party (`https://code.claude.com/docs/en/memory`,
WebFetch 2026-07-29, страница прочитана целиком).

| Факт | Дословно из доки |
|:--|:--|
| `CLAUDE.md` всегда в контексте | «CLAUDE.md files are loaded into the context window at the start of every session»; «CLAUDE.md files are loaded in full regardless of length» |
| Ориентир размера | «target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence» |
| `@import` **не экономит** | «Imported files are expanded and loaded into context at launch alongside the CLAUDE.md that references them»; «Splitting into `@path` imports helps organization but doesn't reduce context, since imported files load at launch». Глубина рекурсии — 4 хопа |
| Вложенные `CLAUDE.md` — ленивые | «Claude also discovers `CLAUDE.md` … in subdirectories under your current working directory. Instead of loading them at launch, they are included when Claude reads files in those subdirectories» |
| `.claude/rules/` существует | Каталог поддержан, `.md` находятся рекурсивно. «Rules without `paths` frontmatter are loaded at launch with the same priority as `.claude/CLAUDE.md`». Path-scoped: «only apply when Claude is working with files matching the specified patterns … trigger when Claude reads files matching the pattern» |
| `AGENTS.md` нативно **не читается** | «Claude Code reads `CLAUDE.md`, not `AGENTS.md`». Рекомендованный паттерн — `@AGENTS.md`-импорт из `CLAUDE.md` либо симлинк |
| HTML-комментарии бесплатны | «Block-level HTML comments (`<!-- maintainer notes -->`) in CLAUDE.md files are stripped before the content is injected into Claude's context» |
| Прочее | `claudeMdExcludes` (исключение чужих файлов в монорепо); `/doctor` с v2.1.206 предлагает трим закоммиченного `CLAUDE.md` |

**Проекция на план.**

1. Правило «корневой контекст — индекс» (принято аудитом, D-лог §4/§11) подтверждено
   первоисточником с числом: **<200 строк**. Живой `CLAUDE.md` — 194 строки / 20 705 байт
   (`findings/01` Ф6), то есть у самой границы при вдвое меньшем полезном ядре.
2. Выносить always-on правила в `@import` **бессмысленно** — экономии нет; это закрывает
   очевидный ложный ход.
3. Управляемые маркеры контракта (`<!-- swissknifeman:instructions:… -->`,
   `<!-- semantic:… -->`, `<!-- instruction:… -->`) — блочные HTML-комментарии, значит
   **вырезаются до инжекта и не стоят ни одного токена** у Claude Code. Управляемость
   бесплатна на стороне Claude.
4. `.claude/rules/` с `paths` — единственный настоящий ленивый носитель у Claude Code, но
   он **Claude-only**: у Codex аналога нет (Ф8), поэтому вынос туда общего правила ломает
   паритет по этому правилу. Двухканальный ленивый носитель у нас один — скиллы
   (публикуются и в `.claude/skills`, и в `.agents/skills`, `findings/01` Ф1).

## Ф8. Codex CLI — модель загрузки инструкций

**Вердикт:** ✅ подтверждён first-party исходником `openai/codex@main` (курл raw-файлов
2026-07-29) + справочником конфигурации `learn.chatgpt.com/docs/config-file/config-reference`
(перенаправление с `developers.openai.com/codex/config-reference`).

| Факт | Первоисточник |
|:--|:--|
| Бюджет проектных доков — **32 KiB** | `codex-rs/config/src/config_toml.rs:68` — `pub const DEFAULT_PROJECT_DOC_MAX_BYTES: usize = 32 * 1024;` |
| Фолбэк-имена по умолчанию — **пусто** | `config_toml.rs:78-80` — `default_project_doc_fallback_filenames() -> Some(Vec::new())`; док: «Additional filenames to try when `AGENTS.md` is missing». То есть **`CLAUDE.md` Codex не читает**, пока пользователь явно не впишет его в `project_doc_fallback_filenames` |
| Корень проекта — по `.git` | `config_toml.rs:465-468` — «Markers used to detect the project root … Defaults to `[".git"]` when unset» |
| Локальный override | `codex-rs/core/src/agents_md.rs:40` — `LOCAL_AGENTS_MD_FILENAME = "AGENTS.override.md"` |
| Обход root→cwd, конкатенация | `agents_md.rs:153-155` — «Discovers AGENTS.md files from the project root to the current working directory, inclusive»; `agents_md.rs:42-44` — доки конкатенируются разделителем |
| Усечение при исчерпании бюджета | `agents_md.rs:106-128` — общий `remaining`, `data.truncate(remaining)`, лог «project doc exceeds remaining budget; truncating» |

**Проекция на план.**

1. Пакетные `AGENTS.md` **работают** и подхватываются при запуске Codex внутри пакета —
   строка router'а живого `AGENTS.md:37` («restart with `codex -C packages/<name>`»)
   соответствует первоисточнику. Значит пять отсутствующих пакетных `AGENTS.md` — реальный
   разрыв, а не косметика.
2. У Codex есть **жёсткий байтовый потолок** на весь стек проектных доков (32 KiB,
   общий на root→cwd) с молчаливым усечением хвоста. У Claude Code такого потолка нет
   (грузится целиком). Это асимметрия не в пользу «просто скопировать `CLAUDE.md`»: при
   работе внутри пакета в бюджет складываются root + пакетный доки.
3. Нынешняя суммарная цена Codex-стека: root `AGENTS.md` 7 501 байт + пакетного нет =
   7.3 KiB из 32 KiB. После принятия канона (замер `research/04`): root 4 340 + пакетный
   ~2 000–2 500 = ~6.7 KiB — то есть механизм не приближает к потолку, а отдаляет.
4. Фолбэка на `CLAUDE.md` нет ни у одного провайдера в обе стороны: Claude не читает
   `AGENTS.md`, Codex не читает `CLAUDE.md`. Два носителя обязаны нести общий смысл сами —
   ровно то, что и постулирует замороженный `provider-instruction-contract`.

## Не проверено (риск принят явно)

- `[UNVERIFIED]` Поведение Codex при `AGENTS.override.md` в нашем дереве не проверялось
  живым прогоном — файла нет, механизм взят из исходника.
- `[UNVERIFIED]` Точная версия Codex CLI у владельца не фиксировалась; факты Ф8 сняты с
  `openai/codex@main` на 2026-07-29 и могут опережать установленный бинарь.
- `[UNVERIFIED]` Влияние `claudeMdExcludes`/`--setting-sources` на наши цели не проверялось:
  в план не входит.
