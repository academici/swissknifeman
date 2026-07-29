# P3 слой 1 — фактический листинг флота, гигиена каналов и вендоринг (2026-07-25, второй заход)

Покрывает новые факт-классы **FC-9** (размер каталога навыков: режимы отказа и приёмы сужения) и
**FC-10** (критерий fork vs tracking) карты `research/19-P3-refresh-fact-classes.md`, а также
**repo-замеры**, на которых стоят решения владельца этого захода. Первый заход не переписывается:
`findings/P3-skill-desc-and-mcp-limits.md` §1 остаётся источником first-party механики бюджета.

Все repo-числа получены прогоном на дереве `5b79f926` + рабочем каталоге 2026-07-25; команды
приведены дословно, чтобы замер был воспроизводим.

---

## 1. Repo-замер: реестр целиком и типовой подписчик

Агрегация frontmatter `description` + `when_to_use` по `packages/skiller/skills/*/*/SKILL.md`:

| Величина | Значение |
|:--|--:|
| Скиллов в реестре | **216** |
| Суммарно `description`+`when_to_use` | **46 578 символов** |
| Типовой 5-бакетный php/laravel-подписчик (`general`+`architect`+`system`+`quality`+`php`) | **15 526 символов** |

Топ-бакеты по символам: `general` 22 скилла / 4 753 · `php` 17 / 3 222 · `architect` 15 / 2 986 ·
`quality` 11 / 2 636 · `frontend-vue` 11 / 2 586 · `php-packages` 9 / 2 083 · `oss-dev` 10 / 1 965 ·
`system` 7 / 1 929 · `laravel-architecture` 6 / 1 895 · `devops` 11 / 1 704.

> **Датированная поправка к слою 2 первого захода.** `research/04-P3-listing-budget-and-trim-math.md`
> §1 приводит **46 878** символов и **15 640** у типового подписчика — числа снимались в тот же день
> другим срезом. Повторный замер даёт **46 578** и **15 526**. Расхождение (−300 / −114 симв, 0,6%)
> вердикт не меняет и обе редакции ведут к одному выводу; слой 2 задним числом не переписывается,
> актуальные числа — здесь.

## 2. Repo-замер: ФАКТИЧЕСКИЙ листинг `flexcrm` (самый нагруженный подписчик флота)

Источник состава — `enabledPlugins` в `/home/vostrikov/projects/flexcrm/.claude/settings.local.json`
(23 плагина `@swissknifeman`, все `true`) × `.claude-plugin/marketplace.json` для резолва
плагин→скиллы; локальный канал — `/home/vostrikov/projects/flexcrm/.claude/skills/`.

| Канал | Записей | Символов |
|:--|--:|--:|
| connect (23 плагина, из них `core@` — курируемый набор 9 скиллов) | **125** | **27 439** |
| в т.ч. `core@` (curated, 9 скиллов по ссылкам) | 9 | 2 114 |
| локальные скиллы проекта (`.claude/skills/`, живые записи) | **17** | **5 587** |
| **ИТОГО листинг** | **142** | **≈33 026** |

Против бюджета листинга ≈**10 000** символов (1% от 1M-контекста, first-party §1 первого финдинга)
это **переполнение ×3,3**. Владелец в том же заходе привёл 32 833 симв (то же ×3,3); расхождение
193 симв — разбор YAML-блок-скаляров в двух измерителях, вердикт не меняет.

Крупнейшие вкладчики листинга flexcrm: `php` 17/3 222 · `architect` 15/2 986 · `quality` 11/2 636 ·
`frontend-vue` 11/2 586 · `core@` 9/2 114 · `system` 7/1 929 · `laravel-architecture` 6/1 895 ·
`devops` 11/1 704.

### 2.1 Гранулярность бакетов (repo-факт)

В реестре **12** бакетов с префиксом `frontend-*` плюс сам `frontend`: `frontend` (3 скилла),
`frontend-animations` (1), `frontend-backend` (3), `frontend-figma` (1), `frontend-linting` (4),
`frontend-naive-ui` (1), `frontend-nuxt` (3), `frontend-reka` (1), `frontend-tailwind` (2),
`frontend-vite` (4), `frontend-vue` (11), `frontend-wayfinder` (1). Шесть из тринадцати несут **1–2
скилла**. `flexcrm` включает **8** из них (`frontend`, `-backend`, `-linting`, `-naive-ui`,
`-tailwind`, `-vite`, `-vue`, `-wayfinder`) — то есть 8 из 23 включённых плагинов приносят
30 записей листинга. Аналогично `laravel-*`: 7 бакетов, из них `laravel-filament` и
`laravel-livewire` по 1 скиллу; `flexcrm` включает 6.

### 2.2 Дубли имён между каналами (repo-факт)

Из 17 живых локальных записей `flexcrm` **11 — симлинки** в `../../.ai/skills/`, и ровно **7 из
них носят имена, существующие в реестре** (все в бакете `general`): `writing-style`, `project-map`,
`git-commit-rules`, `spec-interview`, `skills-ssot`, `complex-task-orchestrator`,
`cross-layer-change-checklist`. Остальные 4 (`mcp-development`, `project-structure`,
`testing-rules`, `fortify-development`) — только локальные.

**Важное уточнение, без которого утверждение было бы сильнее факта:** бакет `general` в `flexcrm`
**не включён** (в `enabledPlugins` его нет — вместо него курируемый `core@`), поэтому сегодня эти
семь имён в один листинг **не попадают дважды**. Дубль здесь — не двойная запись в листинге, а
**вторая физическая копия скилла реестра, живущая вне реестра и не обновляемая
`skiller update`**: включение `general` (или добавление одного из семи в `core@`) мгновенно даёт
двойную запись, а до тех пор проект работает по копии неизвестного возраста.

### 2.3 Битые записи вендорного канала (repo-факт, новое)

`/home/vostrikov/projects/flexcrm/.claude/skills/` содержит **58 записей**: 6 реальных каталогов +
**11 живых симлинков** + **41 БИТЫЙ симлинк** на несуществующие цели в `../../.ai/skills/`
(`context-economy`, `compact-responses`, `session-handoff`, `anti-drift`, `laravel`, `docker*`,
`pest-testing`… — полный список снимается
`find .claude/skills -maxdepth 1 -xtype l -printf '%f\n'`).

Битые симлинки в листинг не попадают (нечего читать), то есть бюджет они не тратят — но это
**41 запись, о которой проект «думает», что она подключена**, и первый же `ls .claude/skills`
создаёт ложную картину покрытия. Среди битых — `context-economy` и `compact-responses`, то есть
CORE-скиллы, которые сюда приезжают каналом `core@`: локальные копии тех же имён просто мертвы.

### 2.4 Что видит наш собственный тулинг (repo-факт, расхождение)

Прогоны 2026-07-25:

```
bash packages/skiller/bin/skiller budget --first-turn --target <project> --json
bash packages/skiller/bin/skiller status --target /home/vostrikov/projects/flexcrm
```

| Проект | skills | agents | claude_md | hooks | mcp | total | verdict |
|:--|--:|--:|--:|--:|--:|--:|:--|
| flexcrm | 5 540 (86 скиллов) | 940 | **15 141** | 387 | 7 500 | 29 508 | WARN |
| sova | 5 540 (86 скиллов) | 0 | **17 767** | 0 | 2 250 | 25 557 | WARN |
| swissknifeman | 2 540 (37 скиллов) | 567 | 4 203 | 1 156 | 5 250 | 13 716 | WARN |
| corex | 5 048 (76 скиллов) | 0 | 1 606 | 0 | 5 250 | 11 904 | WARN |

Три факта из этой таблицы:

1. **`_measure_skills` не видит фактический листинг.** На `flexcrm` он объявляет **86 скиллов**,
   тогда как листинг несёт **142**; `flexcrm` и `sova` дают **байт-в-байт одинаковые** 5 540 ток /
   86 скиллов при разных наборах плагинов (23 против 22). Причина repo-grounded: `_measure_skills`
   → `load_config` → `resolve_active_set` резолвит набор по **профилю/`.swissknife.json`**
   (`packages/skiller/lib/skiller/config.py:157`), а `enabledPlugins` целевого проекта не читает
   вовсе (`grep -rn enabledPlugins packages/skiller/lib/` — только `connect.py`, `update.py`,
   `status.py`, `registry.py`). Это тот же класс переучёта, что первый заход поймал у суммы
   описаний (D22), но с другой стороны: не «сумма вместо бюджета», а «чужой набор вместо
   фактического». Адресат — **P3.4**.
2. **Скиллы — НЕ крупнейший always-on вкладчик у нагруженных подписчиков.** На `flexcrm` и `sova`
   первое место занимает `CLAUDE.md` (15 141 / 17 767 ток), при том что резидент скиллов ограничен
   сверху бюджетом листинга (≈10 000 симв ≈ 2,5–3K ток). Вывод для порядка рычагов P3.1: сжатие
   описаний конкурирует за третье-четвёртое место, а не за первое.
3. **Все четыре проекта — `WARN`** (порог `FIRST_TURN_WARN = 10 000`), включая сам монорепо.

`skiller status --target flexcrm` печатает канал marketplace (23 плагина, профиль
`laravel-project` via autodetect, «Сверх профиля: 14 плагинов») — и **не печатает вендорный канал
вообще**: `detect_vendor_path` не находит его (в `flexcrm` нет `.swissknifeman/config.json`, а
записи живут симлинками из `.ai/skills`), поэтому существующая проверка `channel_overlap`
(`status.py:150`, «ДУБЛЬ КАНАЛОВ … скиллы раздаются дважды») на этом проекте — **молчаливый
no-op**. Проверка существует, но именно там, где дубли есть, она не срабатывает.

## 3. FC-9 — размер каталога навыков: режимы отказа и приёмы сужения (RAG)

RAG:✅ 2026-07-25 perplexity-web (web+social). Источники, названные движком:
`github.com/orgs/community/discussions/182117` (обсуждение нестабильной активации Claude Skills),
`zenn.dev/seiwan/articles/claude-code-utilize-1` (практика Claude Code 2026), плюс сослался на
исследование конфигураций по 2 926 репозиториям и наблюдательное исследование 20 574 сессий
coding-агентов.

**Дословно значимое:**

- Прямого числа «после N навыков выбор деградирует» **не существует**: «There is still no solid
  public benchmark that says "selection reliability drops after exactly N skills." The available
  evidence is mostly indirect». Помечено как **не найдено** — любой порог у нас обязан опираться на
  собственный замер (`/doctor` + строка Skills в `/context`), а не на это.
- Наблюдаемая практика: Skills — среднее **3,8** на репозиторий, медиана **2**, большинство
  проектов держат **менее 3**; Subagents — среднее 3,45, медиана 2. «83.3% of Skills had no
  additional resources». То есть наши 142 записи на проект — на два порядка выше отраслевой
  медианы.
- Названные режимы отказа «подключили всё»: **description dilution** и нестабильная активация
  («large skill catalogs create description dilution and unstable activation»); «when skills grow to
  dozens, the description metadata itself becomes a burden on the context and the bigger issue
  becomes **the decreased probability of the AI calling the intended skill**».
- Названные приёмы сужения (в порядке, в котором их предъявляет практика): **консолидация
  микро-скиллов в макро-скиллы** («the agent is much more likely to retrieve one comprehensive
  document» than several fragmented ones; «merging tightly coupled micro-skills into a single
  standard and using better use-case metadata so retrieval has fewer, stronger candidates») ·
  **progressive disclosure** (тонкая точка входа + тело по требованию) · **router / lazy
  disclosure** («expose only a name plus a short descriptor at startup») · «one global instruction
  file, a few macro-skills, and on-demand subfiles or subagents behind a router».
- Итоговое правило источника: «keep the visible catalog small, make entries semantically distinct,
  and move breadth behind lazy retrieval».

**Следствия для нас (синтез, не цитата):**

1. Режим отказа, названный практикой, **совпадает с механикой, названной first-party**: клиент
   роняет описания «starting with the skills you invoke least», а практика независимо фиксирует
   «decreased probability of calling the intended skill». Два разных класса источника указывают на
   один дефект — **качества, а не экономии**.
2. Приём «консолидация микро-скиллов» напрямую бьёт в наш repo-факт §2.1: шесть `frontend-*`
   бакетов по 1–2 скилла.
3. Приём «name-only + router» у нас существует как **готовый first-party рычаг**
   (`skillOverrides: "name-only"`), то есть отраслевую практику можно применить настройкой, а не
   переписыванием 216 файлов.
4. Порядок рычагов, который владелец зафиксировал решением (сузить набор → name-only → бюджет →
   сжать текст), — **отраслевой, а не наш**: практика ставит сужение и lazy-раскрытие ВЫШЕ правки
   текстов.

## 4. FC-10 — критерий fork vs tracking для вендоренного внешнего (RAG)

RAG:✅ 2026-07-25 perplexity-web (web+social). Названные источники: обсуждение rOpenSci 2025 о
сопровождении форков, руководство GitHub по fork-management.

**Дословно значимое:**

- Базовое правило: «if divergence is meant to be temporary or low-volume, track upstream; if the
  customization is structural, long-lived, or upstream cannot or will not take it, treat it as a
  fork and budget for permanent maintenance».
- Цена форка называется тремя частями: **permanent merge tax · drift · security backports**. «the
  more upstream changes accumulate since the last sync, the harder the merge becomes»; «once a fork
  diverges too far, contributing back becomes harder».
- Числовых порогов практика не даёт: «There are few universal numeric thresholds». Вместо порога —
  три эвристики: **minimize the diff surface** («if your patch set touches many files or core
  abstractions, expect fork pain; if most changes live in one or two seams, upstream tracking is
  much easier»), **cadence-based** (проактивный fork синкается на каждый релиз апстрима, осторожный
  сознательно отстаёт на 1–2 релиза), **patch-queue discipline** (держать правки отдельной
  воспроизводимой очередью, а не вплетать в историю).
- Операционный критерий вместо числа: «once the marginal cost of staying current is routinely
  higher than the value of upstream compatibility, the fork has become the correct operational
  choice»; ключевой вопрос сопровождения — «can this change be re-applied **mechanically** after an
  upstream update, or does it require human judgment every time?»
- Средний путь назван прямо: **vendor branch / patch queue** — «keep the upstream code close to
  pristine, apply your downstream patches as a separate, replayable series, and **regenerate
  derived artifacts rather than editing them by hand**».

**Следствия для нас (синтез):**

1. Наш `strategy` — это ровно ось «tracking (`notify`/`replace`) vs ownership (`fork`)», а
   `merge` — реализация «vendor branch + patch queue» (несколько origins, ручной агент-мерж).
   Термины совпадают, изобретать словарь не нужно.
2. Практика **отказывается** давать числовой порог — значит и наш критерий обязан быть
   двухосевым и операционным («можно ли переприменить механически» × «сколько стоит следующий
   синк»), а не «N расхождений ⇒ fork».
3. «Regenerate derived artifacts rather than editing them by hand» — это наша уже действующая
   рамка (`skiller registry`, двуязычная модель `SKILL.ru.md` → `SKILL.md`), то есть у нас
   patch-queue-дисциплина частично есть.

## 5. Repo-замер: фактическое состояние вендоринга

```
ls packages/skiller/skills/*/*/upstream.json | wc -l            # 56
python3 -c "...Counter(strategy)..."                            # notify 54, fork 1, replace 1
```

| Величина | Значение |
|:--|:--|
| Всего `upstream.json` | **56** (из 216 скиллов; локальных RU-источников — 160) |
| `strategy=notify` | **54** |
| `strategy=fork` | **1** — `skills/ai/ai-agents` (`get-zeked/ai-agent-super-skill`, MIT, `review_pending: false`) |
| `strategy=replace` | **1** — `skills/ai/mcp-builder` (`anthropics/skills`, Apache-2.0) |
| `strategy=merge` | **0** (форма реализована, ни одного носителя) |

Механика — `packages/skiller/scripts/update-upstreams.sh`: `--apply` для `replace` перезаписывает
локальный файл и пишет `sha256`/`fetched_at`; для `notify` фиксирует увиденный upstream-sha, файл не
трогает; для `fork` кладёт апстрим как `upstream/<name>.incoming` и требует ручной доработки; для
`merge` при дрейфе ЛЮБОГО origin ставит `merge.review_pending=true` (гейт, блокирующий
`validate.sh`/`registry`/релиз), `--resolve` промотирует. Валидатор знает enum из четырёх значений
(`packages/skiller/scripts/validate.sh:65` — `{"replace","notify","fork","merge"}`).

**Расхождение доки с кодом (repo-факт):** корневой `CLAUDE.md` § «Референсы и провенанс» называет
`strategy` = `notify | fork | merge` — **`replace` в перечне отсутствует**, хотя это единственная
стратегия с авто-перезаписью и она используется на дереве. Носитель дефекта — корневой `CLAUDE.md`
(always-on файл), исправление — одна правка перечня.

**Текущий фон гейта (repo-факт):** `bash packages/skiller/scripts/validate.sh` 2026-07-25 —
`217 skills checked — all valid (67 warning(s))`, `registry --check: артефакты актуальны`,
`tests: OK (Ran 418 tests)`, `CORE резидент (⊕ tier-0): 663 ток / target 750 — OK (9/9)`,
`внешних: 56 (с RU-справкой: 55)`.

## 6. Repo-замер, опровергающий несущий пункт действующего ТЗ P3.1

Действующее ТЗ P3.1 (`phases/P3.md`, Implementation Rules) утверждает: «Восемь уже протухших строк
(скиллы удалены: `architect/dev-engineering-super-skill`, `pm/pm-super-skill`, `ai/token-efficient`,
`sales/sales-super-skill`, `creative/content-creative-super-skill`, `finance/finance-super-skill`,
`security/agent-security-super-skill`, `operator/operations-cx-super-skill`) вычищаются в этом
item'е в любой ветке вердикта».

**Утверждение неверно. Все восемь скиллов живы.** Ключ рэтчета — `<bucket>/<name>` из
**frontmatter**, а не путь каталога (шапка `scripts/desc-burndown.txt` говорит это дословно:
«совпадает с frontmatter bucket:name»). У всех восьми был переименован КАТАЛОГ, а frontmatter
`name` сохранён:

| Ключ рэтчета | Фактический путь | `description` |
|:--|:--|--:|
| `architect/dev-engineering-super-skill` | `skills/architect/engineering/SKILL.md` | 421 |
| `pm/pm-super-skill` | `skills/pm/product/SKILL.md` | 391 |
| `ai/token-efficient` | `skills/ai/performance/SKILL.md` | 361 |
| `sales/sales-super-skill` | `skills/sales/sales/SKILL.md` | 348 |
| `creative/content-creative-super-skill` | `skills/creative/content-creative/SKILL.md` | 347 |
| `finance/finance-super-skill` | `skills/finance/finance/SKILL.md` | 335 |
| `security/agent-security-super-skill` | `skills/security/security/SKILL.md` | 323 |
| `operator/operations-cx-super-skill` | `skills/operator/operations-cx/SKILL.md` | 305 |

Все восемь: `description` в диапазоне **>300 и ≤450**, то есть по правилу рэтчета легальны
**только пока строка в списке**. Удаление восьми строк, как предписывает действующее ТЗ, превратило
бы восемь `WARN` в восемь **hard ERROR** и уронило бы `validate.sh` — то есть исполнение ТЗ
дословно ломает гейт.

Авторитетный источник «протухла ли запись» — сам гейт: прогон `validate.sh` 2026-07-25 печатает
**ни одной** строки «протухшая запись», а `--- 67 warning(s)` целиком состоят из легального
унаследованного долга. Фактически протухших строк в `desc-burndown.txt` (64 записи) — **ноль**.

**Класс ошибки назван:** вывод «скилл удалён» был сделан по отсутствию КАТАЛОГА
(`research/04-P3-listing-budget-and-trim-math.md` § «Побочный repo-факт»), тогда как гейт ключует
по frontmatter. Это ровно тот случай, который дисциплина `verify-claims` относит к repo-grounded
фактам, подтверждаемым чтением кода: правило рэтчета было в шапке файла и не было прочитано.
Слой 2 первого захода задним числом не переписывается — поправка живёт здесь.
