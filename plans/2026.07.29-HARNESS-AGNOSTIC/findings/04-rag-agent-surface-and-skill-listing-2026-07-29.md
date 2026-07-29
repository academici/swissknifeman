# RAG-разведка: платформенная поверхность агентов и бюджет обнаружения скиллов — 2026-07-29

Слой 1 (внешнее сырьё). Прогон выполнен сессией авторинга фазы P3 (Opus 5/high) по лестнице
`perplexity-web → WebFetch first-party`. Дисциплина унаследована от `2026.07.18-FOREMAN` D19:
Perplexity-факт в несущей позиции обязан быть подтверждён first-party — здесь подтверждены
ВСЕ несущие факты (Ф13–Ф17), кроме явно помеченных `[UNVERIFIED]`.

Зачем: фаза P3 приводит `packages/skiller/docs/agent-framework/*` к правде. Половина
утверждений этих документов — внешние (платформенные), и переписывать их «по дереву»
нельзя: дерево про них ничего не знает. Ниже — first-party срез на дату фазы.

---

## Ф13. Бюджет обнаружения скиллов у Codex — first-party, прямое чтение

**Вердикт:** ✅ подтверждён прямым WebFetch (ранее — Ф4 `findings/01`, через цитирующий
поиск Perplexity; теперь первоисточник прочитан напрямую).

Источник: `https://learn.chatgpt.com/docs/build-skills` (WebFetch, 2026-07-29). Дословно:

- «The skills list uses at most **2 % of the model's context window, or 8 000 characters
  when the context window is unknown**.»
- «If many skills are installed, **Codex shortens skill descriptions first. For large skill
  sets, Codex may omit some skills from the initial list and show a warning.**»
- «This budget applies only to the initial skills list. **When Codex selects a skill, it
  still reads the full `SKILL.md`** instructions for that skill.»
- Ограничения на размер самого `SKILL.md` в доке **нет**.

**Следствия для плана.** (1) Тезис «8 KB — жёсткий лимит тела `SKILL.md`» опровергнут
окончательно и первоисточником (закрывает OQ-4: кап тела вводить не на что). (2) Режим
деградации у Codex **хуже**, чем у Claude Code: тот всегда перечисляет ИМЕНА и режет только
описания, Codex же может **выбросить скилл из листинга целиком**. То есть перебор бюджета
обнаружения — это не «менее точный выбор», а «скилл невидим», и это разрыв паритета,
измеряемый арифметикой, а не мнением.

## Ф14. Бюджет обнаружения скиллов у Claude Code — first-party

**Вердикт:** ✅ подтверждён WebFetch `https://code.claude.com/docs/en/skills` (2026-07-29).

- «Claude Code loads a listing of skill names and descriptions into context… **The listing
  always contains every skill name**, but if you have many skills, Claude Code shortens
  descriptions to fit the listing's character budget… **The budget scales at 1 % of the
  model's context window.** When the listing overflows, Claude Code **drops descriptions
  starting with the skills you invoke least**.»
- Потолок записи: «the combined `description` and `when_to_use` text is **truncated at
  1 536 characters** in the skill listing»; настраивается `skillListingMaxDescChars`.
- Рычаги: `skillListingBudgetFraction` (напр. `0.02`), env `SLASH_COMMAND_TOOL_CHAR_BUDGET`
  (фиксированное число символов), `skillOverrides: "name-only"` — перевести
  низкоприоритетные записи в режим «только имя» и освободить бюджет остальным.
- Диагностика: `/doctor` даёт оценку стоимости листинга и его главных вкладчиков; при
  переборе Claude Code пишет предупреждение в debug-лог (`--debug`); строка `Skills` в
  `/context` показывает размер ПОСЛЕ применения бюджета (до v2.1.196 — до применения).

**Следствие.** Модель, зашитая в `packages/skiller/lib/skiller/budget.py`
(`SKILL_LISTING_BUDGET_FRACTION = 0.01`, `SKILL_LISTING_MAX_ENTRY_CHARS = 1 536`), совпадает
с первоисточником и на 2026-07-29 не протухла. Не хватает ровно одного: модели ВТОРОГО
провайдера (Ф13) — иные и доля (2 %), и фолбэк (8 000 символов), и режим деградации
(выброс скилла, а не усечение описания).

## Ф15. Преднагрузка скиллов в субагента (`skills:`) — first-party

**Вердикт:** ✅ подтверждён WebFetch `https://code.claude.com/docs/en/sub-agents` (2026-07-29).

- Поле `skills` во frontmatter субагента существует: «Skills to preload into the subagent's
  context at startup. **The full skill content is injected**, not only the description.»
- Поведение на неизвестном/выключенном имени: «**If a listed skill is missing or disabled,
  Claude Code skips it and logs a warning to the debug log.**» — то есть «молчаливый no-op»
  из `decisions-ledger.md` подтверждён по сути: видимой ошибки нет, только debug-лог. Сверка
  имён `skills:` с реестром (реализована в `generate-hub.sh` и `skiller doctor`) остаётся
  единственным способом поймать это до прогона.
- Нельзя преднагружать скиллы с `disable-model-invocation: true` (и бандлы `/verify`,
  `/code-review`, v2.1.215+).

## Ф16. Agent Teams — first-party срез на 2026-07-29

**Вердикт:** ✅ подтверждён WebFetch `https://code.claude.com/docs/en/agent-teams` (2026-07-29).

| Утверждение | Статус |
|:--|:--|
| Экспериментально, выключено по умолчанию, включается `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | ✅ актуально |
| Страница описывает поведение «as of v2.1.178»; `TeamCreate`/`TeamDelete` **больше не существуют**, `team_name` на Agent-туле принимается и игнорируется | ⚠ ново относительно нашего канона |
| **Дефолт `teammateMode` — `in-process`; до v2.1.179 дефолтом было `auto`** | ⚠ наш канон описывает старый дефолт |
| `iterm2` как явный режим — с v2.1.186 (требует `it2` CLI) | ⚠ ново |
| Хук-события команды: **`TeammateIdle`, `TaskCreated`, `TaskCompleted`** | ⚠ наш канон знает только два из трёх |
| **Поля `skills` и `mcpServers` определения субагента НЕ применяются, когда это определение запущено как teammate**: «Teammates load skills and MCP servers from your project and user settings, the same as a regular session» | ⚠ **несущее** — прямо ограничивает наш тезис «роли каркаса годятся как teammates без изменений» |
| Teammates не наследуют `/model` лида (выбирается в `/config` или в промте); **effort лида наследуют** (в split-pane — с v2.1.186) | ⚠ первая половина в каноне есть, вторая — нет |
| Вложенных команд нет; лид фиксирован; `/resume` не восстанавливает in-process teammates; split-pane требует tmux/iTerm2 | ✅ / ⚠ частично в каноне |
| Рекомендуемый размер команды — 3–5 teammates, 5–6 задач на teammate | ⚠ ново |

**Следствие для каркаса.** Модель ролей опирается на `skills:` preload из профиля пака. В
режиме teammate этот preload **не применяется** — работает только self-load fallback в теле
промта роли (он в `roles.md` уже предусмотрен). Значит утверждение `agent-teams.md` «роли
годятся как teammates без изменений» истинно только с этой оговоркой, и оговорка обязана
быть записана: без неё модель ролей молча деградирует на втором способе исполнения.

## Ф17. Лимиты субагентов — first-party (обновились относительно канона)

Источник: `https://code.claude.com/docs/en/sub-agents` (WebFetch, 2026-07-29).

| Лимит | Значение | Настройка | Версия |
|:--|:--|:--|:--|
| Всего субагентов за сессию | **200** | `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` | v2.1.212+ |
| Одновременно | **20** | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | v2.1.217+ |
| Глубина вложенности | **3** (v2.1.217–218 было 1; до v2.1.172–216 — 5, неизменяемо) | — | v2.1.219 |

Агенты, порождённые скриптом workflow через `agent()`, в счёт сессии **не идут** — у
workflow свой per-run лимит. То есть цифра канона «~16 конкуррентно / 1000 на прогон»
описывает **workflow-рантайм**, а не Agent-тул, и смешивать их в одной строке нельзя: для
политики спавна (фаза P4) это два разных потолка.

## Ф18. `.claude/rules/` — подтверждение актуальности

`.claude/rules/` с frontmatter `paths:` — по-прежнему нативный механизм (Perplexity
2026-07-29 со ссылкой на `code.claude.com/docs/en/memory`; first-party этой же страницы уже
прочитан в `findings/02` Ф7: правила без `paths` грузятся безусловно на старте, path-scoped
— при чтении подходящего файла). Для плана существенно то же, что и в P1: у Codex аналога
нет, поэтому носителем ОБЩИХ правил `.claude/rules/` быть не может (D15).

## Замеры реестра (repo-grounded, 2026-07-29)

Приведены здесь, потому что смысл им придают Ф13/Ф14.

| Замер | Результат |
|:--|:--|
| Скиллов в реестре | 229 (`find packages/skiller/skills -name SKILL.md \| wc -l`), 49 бакетов |
| `description`: сумма / среднее / медиана / max / min | 50 117 / 219 / 212 / 421 / 41 символов |
| Записей > 1 024 симв (потолок Cursor/OpenCode) и > 1 536 (потолок записи Claude Code) | 0 и 0 |
| Описаний < 100 симв | 40 |
| Описаний без триггерной фразы (`use when`/`activate`/`when you`/`whenever`/…) | 126 из 229; из них < 100 симв — 40, а без upstream-скиллов (их канон не правится) — **39** — это blocker-набор P3.5 |
| Существующий гейт длины | `validate.sh` §1: `DESC_ERROR_MAX = 450` (hard), `DESC_WARN_MAX = 300` + one-way рэтчет `scripts/desc-burndown.txt` (83 строки, bootstrap 2026-07-12) |

**Листинг обнаружения по профилям** (`name` + `description` + путь, символы; расчёт —
по бакетам профиля):

| Профиль | Бакетов | Скиллов | Листинг, симв | Против Codex (8 000) | Против Claude Code (1 % окна) |
|:--|--:|--:|--:|:--|:--|
| `standalone` | 1 | 0 | 0 | ок | ок |
| `blender` | 4 | 21 | 6 303 | ок (79 %) | ок |
| `dart-flutter` | 4 | 34 | 10 379 | **перебор ×1.3** | ок при окне 1M |
| `node-package` | 4 | 39 | 10 903 | **перебор ×1.4** | ок при окне 1M |
| `python-backend` | 6 | 52 | 13 990 | **перебор ×1.7** | ок при окне 1M |
| `obsidian-vault` | 12 | 59 | 14 947 | **перебор ×1.9** | ок при окне 1M |
| `php-package` | 7 | 69 | 19 530 | **перебор ×2.4** | ок при окне 1M |
| `node-frontend` | 9 | 68 | 19 859 | **перебор ×2.5** | ок при окне 1M |
| `laravel-project` | 9 | 76 | 20 921 | **перебор ×2.6** | ок при окне 1M |
| `platform-service` | 10 | 104 | 29 498 | **перебор ×3.7** | ок при окне 1M |

Читать так: при окне 1M у Claude Code бюджет ≈ 10 000 токенов (~40 000 симв) — ни один
профиль его не пробивает; при окне 200K бюджет ≈ 2 000 токенов (~8 000 симв) — пробивают
восемь из девяти. У Codex фолбэк 8 000 символов пробивают восемь из девяти профилей
**при любом окне**, а 2 % окна спасают только при окне ≥ 1M символов эквивалента.

## Не проверено (риск принят явно)

- `[UNVERIFIED]` Живой прогон Codex CLI с установленным реестром: сколько скиллов реально
  выбрасывается из листинга и как выглядит предупреждение — замера не делалось (round-trip
  вне скоупа плана, D3).
- `[UNVERIFIED]` Размер контекстного окна, который Codex CLI считает «известным» для
  текущей модели: от этого зависит, работает ли правило «2 %» или фолбэк 8 000 символов.
  Расчёты выше сознательно ведутся по фолбэку как по худшему случаю.
- `[UNVERIFIED]` Учитывает ли листинг Codex путь скилла и служебные разделители дословно;
  наш расчёт `name + description + путь` — верхняя оценка того же порядка.
- `[UNVERIFIED]` Порядок «дропа» описаний у Claude Code зависит от истории вызовов проекта,
  которой у нас нет, — измеряется потолок, а не конкретные выпавшие записи (то же
  ограничение уже зафиксировано в `budget.py`).
