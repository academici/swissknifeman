# P5 / OQ-6 — фактура ремедиации (замеры 2026-08-01)

Слой 1 (сырьё). Собрано заходом `plan-design 2026.07.31-SKM-LEAN P5` при закрытии гейта
владельца **OQ-6**. Потребители — items **P5.10** и **P5.11**, D107–D110.

Все числа сняты собственным прогоном на рабочем дереве (`HEAD = c615ddcb`, ветка `main`),
команды приведены дословно — воспроизводимы без этой сессии.

---

## 1. Носитель находки §3.1 — бандл `frontend/web-design-guidelines`

```
$ ls -la packages/skiller/skills/frontend/web-design-guidelines/
SKILL.md      1231 б
SKILL.ru.md   2234 б
SYNC.md        170 б
upstream.json  561 б
```

`upstream.json` на момент замера (дословно, ключевое):

```json
{ "schema_version": 1, "source": "github", "repo": "antfu/skills",
  "strategy": "notify", "license": "MIT",
  "files": [ { "path": "SKILL.md",
    "url": "https://raw.githubusercontent.com/antfu/skills/main/skills/web-design-guidelines/SKILL.md",
    "sha256": "f4647ca866a3accf763777f83e7682954f0187cd6bea7eea0399796652414e8f",
    "fetched_at": "2026-06-17" } ] }
```

**Два разных апстрима в одном бандле.** Сам бандл импортирован из `antfu/skills`
(`strategy=notify` — дрейф только рапортуется). А правила, которым агент следует, лежат в
ТРЕТЬЕМ репозитории — `vercel-labs/web-interface-guidelines`, и `upstream.json` о нём не
знает вообще: sha256 покрывает 1 231 байт обёртки, а не 6 939 байт правил.

`SKILL.md:16–29` дословно:

```
Fetch fresh guidelines before each review:
https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
Use WebFetch to retrieve the latest rules. The fetched content contains all the rules
and output format instructions.
```

`SKILL.ru.md:31` несёт ту же инструкцию по-русски (поэтому у правила триажа
`PRM_REMOTE_INSTRUCTIONS` есть RU-ветка — иначе гейт молчал бы на половине поверхности).

## 2. Замер удалённого payload (живой прогон, 2026-08-01)

```
$ curl -sS https://api.github.com/repos/vercel-labs/web-interface-guidelines/commits/main
sha  = 4e799d45c17aec1498c269287a83b9dba22b966b
date = 2026-04-06T22:11:41Z          # HTTP 200

$ curl -sS https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/\
4e799d45c17aec1498c269287a83b9dba22b966b/command.md
http = 200   bytes = 6939
sha256 = eea73cb6dd46fee9faec9973e8e7fe198b5f07ec326f14d276a56e50287e1cab
```

Содержимое — markdown с YAML-frontmatter (`description`, `argument-hint`) и списком правил
Accessibility / Forms / Animation / Layout / Content / Performance / Design. Ничего
исполняемого, `$ARGUMENTS`-шаблон команды. **6,9 КБ** — вендоринг стоит копейки.

**Замечание к свежести:** `main` не двигался с **2026-04-06** — то есть «fetch fresh before
each review» уже четыре месяца возвращает один и тот же байт-в-байт файл. Цена пиновки в
терминах актуальности на замере равна нулю.

## 3. Внешняя опора решения — иммутабельность SHA-пинованного raw-URL

**RAG:✅ 2026-08-01** (perplexity-web; запрос: «raw.githubusercontent.com с полным 40-символьным
commit SHA — иммутабелен ли против ветки `/main/`, оговорки: force-push, удаление репозитория,
CDN-кеш»). Вердикт источника: URL с полным commit SHA **пинует состояние репозитория на этом
коммите** и не следует за движением ветки, потому что ветка — это перезаписываемый ref
(«can be rewritten to point to a new commit»), а SHA коммита уникален.

**Названные оговорки (перенесены в ТЗ как границы, а не замолчаны):**
1. удаление/приватизация репозитория ломает URL независимо от формы ссылки;
2. edge-кеш raw-эндпойнта существует, но для SHA-URL он безопасен — меняться содержимому
   уже неоткуда;
3. SHA-URL пинует **репозиторий**, а не независимо хранимый артефакт: гарантия внешняя.

Именно из-за (1) и (3) пиновки URL **недостаточно** — целостность обязана держаться на НАШЕЙ
стороне: sha256 в `files[]` над локально лежащими байтами. Пиновка убирает подмену контента,
вендоринг убирает зависимость от чужой доступности; ни одно из двух не заменяет другое.

## 4. Как устроен `strategy=fork` — образец для копирования

Живой образец в реестре ровно один — `packages/skiller/skills/ai/ai-agents/upstream.json`:

```json
{ "schema_version": 1, "source": "github", "repo": "get-zeked/ai-agent-super-skill",
  "strategy": "fork", "review_pending": false, "last_review": "2026-06-25",
  "license": "MIT",
  "files": [ { "path": "references/source.md",
    "url": "https://raw.githubusercontent.com/get-zeked/ai-agent-super-skill/main/SKILL.md",
    "sha256": "cfd45bc…", "fetched_at": "2026-06-25" } ],
  "notes": "Форк …: SKILL.md — тонкая обёртка-навигатор, полный апстрим зеркалится в
            references/source.md (pristine). Апстрим не накатывать автоматом …" }
```

Механика, прочитанная в носителях (`update-upstreams.sh:1–26,477–502`,
`validate.sh:452–465,515–566`):

- `files[].path` при `fork` по конвенции указывает на **pristine-зеркало** в `references/`,
  а `SKILL.md` — рукописная обёртка, которую скрипт никогда не перезаписывает;
- `--apply` при `fork` не пишет в дерево: он кладёт `upstream/<name>.incoming` и ставит
  `review_pending: true`;
- `review_pending: true` — **гейт**: `validate.sh` даёт ERROR, а значит блокируется реестр и
  релиз, пока агент не перенесёт дифф и не сделает `--resolve`;
- **`body_path`** (аддитивное поле, P7.3) явно называет, КАКАЯ запись `files[]` является
  «телом» апстрима, когда `SKILL.md` стал навигатором; `validate.sh:551` требует, чтобы
  `body_path` совпадал с одной из `files[].path` — иначе дрейф тела не отслеживается;
- число записей `files[]` не ограничено: общий цикл считает sha/дрейф поштучно.

Проверка контрактов потребителей `upstream.json`:

```
$ grep -n "strategy" packages/skiller/scripts/validate.sh   # → UPSTREAM_STRATEGIES
```

`validate.sh` **не запрещает неизвестные ключи верхнего уровня** (проверяются
`schema_version`, `source`, `strategy`, `files[]`, `origins[]`/`merge` при `merge`,
`body_path`) — значит аддитивный блок `audit` схему не ломает, но и не проверяется ничем,
пока для него не добавлена собственная валидация. Это вход P5.11, а не разрешение
«положить и забыть».

## 5. Как сегодня устроено протухание вердикта (и где у него дыра)

`update-upstreams.sh:571–592`, дословно из комментария носителя:

> `audited_at` таблицы вердиктов несёт тот самый sha256, который в момент аудита лежал в
> `files[].sha256`. Значит дрейф относительно записанного sha И ЕСТЬ дрейф относительно
> `audited_at`. … **ГРАНИЦА:** после `--apply` свежий sha записывается в `upstream.json`,
> дрейф исчезает — и отметка вместе с ним, хотя человеческий вердикт остался протухшим.

То есть механизм **производный**: он не хранит собственного якоря, а выводит его из
совпадения, которое `--apply` разрушает одной строкой. Второй дырой того же класса является
отсутствие признака «вердикта не было никогда»: бандл, добавленный завтра, отличается от
проверенного человеком только тем, что о нём никто ничего не записал, — и `--check` об этом
молчит. Оба следствия — вход **P5.11**.

## 6. Знаменатель и класс `reference-only` (§3.6 отчёта аудита)

```
$ find packages/skiller/skills -name upstream.json | wc -l      → 56
```

Из 56 как минимум один (`voice-ai/voice-ai`) не вендорит НИЧЕГО: пять записей `files[]` с
пустыми `path`/`sha256` — это провенанс-ССЫЛКИ на внешние спеки, а `SKILL.md` написан у нас.
`validate.sh:523` пропускает пустой `path` молча (`if path:`), поэтому класс не отличим
машинно, а знаменатель «56 вендоренных бандлов» неоднороден по составу.

Проверка, сколько таких записей в реестре:

```
$ python3 - <<'PY'
import json, pathlib
for f in sorted(pathlib.Path("packages/skiller/skills").rglob("upstream.json")):
    d = json.loads(f.read_text())
    if all(not e.get("path") for e in d.get("files", [])):
        print(f.parent.relative_to("packages/skiller/skills"))
PY
```

## 7. Что этот заход НЕ замерял (границы фактуры)

- **usage вендоренных скиллов** — данных нет ни у этого захода, ни у P5.1; ветка (C) OQ-6
  поэтому не имеет входа и решением не выбиралась;
- **содержимое остальных 55 бандлов повторно не читалось** — вердикты берутся из
  `findings/P5-vendored-audit.md` как есть;
- **живой прогон `--check` после правок** не делался (правок нет — заход проектный).
