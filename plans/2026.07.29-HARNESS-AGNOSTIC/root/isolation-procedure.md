# Изоляция работ плана `2026.07.29-HARNESS-AGNOSTIC` — процедура и обратимость

Носитель D1/D4/D8/D11 (P0.1). Все команды ниже фактически прогнаны; результат вклеен
как есть. Непрогнанный шаг обязан нести `[UNVERIFIED]` — таких шагов нет.

## Проблема

Все пять CLI флота — симлинки в ОСНОВНОЕ рабочее дерево:

```
/home/vostrikov/.local/bin/{swissknifeman,skiller,harness,maind,analyst}
  -> /home/vostrikov/projects/packages/swissknifeman/...
```

Переключение веток в основном каталоге меняет живой инструмент всего флота (25
онбордженных проектов) — изоляции одними ветками недостаточно. Решение (D1/D8): второе
git-дерево (`git worktree`) + отдельный bin-dir, чтобы новый контур не пересекался со
старым ни по коду, ни по симлинкам.

## Создание (уже выполнено фактически, до этого item'а)

```
git worktree list
# /home/vostrikov/projects/packages/swissknifeman                 8e16a811 [main]
# /home/vostrikov/projects/packages/swissknifeman-next             d32fa7f1 [next/harness-agnostic]
```

Два дерева одного репозитория: `swissknifeman` на `main`, `swissknifeman-next` на
`next/harness-agnostic`. Общий `.git` (объекты и рефы), независимые рабочие деревья и
независимо checked-out ветки — стандартное свойство `git worktree`.

## Установка CLI нового контура

Ставится **из каталога worktree** (`swissknifeman-next`), в отдельный bin-dir
`~/.local/bin-skm-next` (D11), командой:

```
cd /home/vostrikov/projects/packages/swissknifeman-next
./install.sh --bin-dir ~/.local/bin-skm-next
```

`~/.local/bin` (старый контур) этой командой не трогается ни при каких условиях;
флаг `--force` в процедуре не используется. Фактический прогон (лог install.sh):

```
Установка CLI пакетов (bin-dir: /home/vostrikov/.local/bin-skm-next):
— skiller:   Установлено: .../bin-skm-next/skiller -> .../swissknifeman-next/packages/skiller/bin/skiller
— harness:   Установлено: .../bin-skm-next/harness -> .../swissknifeman-next/packages/harness/bin/harness
— maind:     Установлено: .../bin-skm-next/maind   -> .../swissknifeman-next/packages/maind/bin/maind
             (создан config.json из example в worktree — package-local файл, не общая поверхность)
— analyst:   Установлено: .../bin-skm-next/analyst -> .../swissknifeman-next/packages/analyst/bin/analyst
— swissknifeman: .../bin-skm-next/swissknifeman -> .../swissknifeman-next/bin/swissknifeman
Готово. CLI: swissknifeman (router) · skiller · harness · maind · analyst
```

## Активация / деактивация контура

Активация — **только префикс PATH в текущей оболочке**, без записи в `~/.bashrc`,
`~/.profile` или `~/.zshrc` (запись сделала бы изоляцию необратимой по умолчанию):

```
PATH="$HOME/.local/bin-skm-next:$PATH"
```

Деактивация — открыть новую оболочку (без префикса) либо `export PATH="${PATH#*:}"`
для точного отката ТОЛЬКО этого добавления в текущей сессии.

Проверка: `grep -n "bin-skm-next" ~/.bashrc ~/.profile ~/.zshrc` — пусто (exit 1), rc-файлы
не тронуты.

## Возврат в основное дерево (P5.2, ОСНОВНОЕ рабочее дерево)

Единственная необратимая граница плана (D43): пять CLI флота и `.mcp.json` онбордженных
проектов зашиты в ОСНОВНОЕ дерево (`/home/vostrikov/projects/packages/swissknifeman`), и его
содержимое переключается для потребителей В МОМЕНТ КОММИТА, ещё до реинсталла. Порядок ниже —
жёсткий: якорь → merge → пост-мердж валидация → смоук ПРЕЖНИМ контуром → (при красном —
откат по якорю).

1. Предусловие: рабочее дерево основного каталога чистое —
   `cd /home/vostrikov/projects/packages/swissknifeman && git status --short` пусто. Непустой
   вывод = чужая работа в дереве → СТОП, не продолжать (владелец правил параллельно).
2. Якорь отката ДО первой мутации: `git -C /home/vostrikov/projects/packages/swissknifeman
   rev-parse --short main` — записать значение в Completion Notes P5.2 и в этот раздел.
3. Merge из основного дерева: `cd /home/vostrikov/projects/packages/swissknifeman && git merge
   --no-ff next/harness-agnostic -F <файл с Conventional Commit RU и PLAN-ID>` (репозиторий
   один — общий `.git` через `git worktree` — обычный локальный merge веток, без сетевого
   fetch). `--squash`/rebase запрещены (D41/провенанс пяти фаз). Конфликт → `git merge --abort`
   + ESCALATION-блок в P5.2, разрешение руками запрещено.

   **Исправлено по факту прогона P5.2 (2026-07-30):** шаг нёс лишний
   `git fetch . next/harness-agnostic:next/harness-agnostic &&` перед merge. Эта команда
   не просто избыточна (ref уже общий), а **невыполнима**: git отказывается обновлять ref
   ветки, выкачанной в другом worktree —
   `fatal: refusing to fetch into branch 'refs/heads/next/harness-agnostic' checked out at
   '/home/vostrikov/projects/packages/swissknifeman-next'` (exit 128), и `&&` оборвал бы
   всю цепочку до merge. Тождественность ref проверяется вместо fetch — обе команды дают
   `acf73d6104c77fd1117ccf5c231134955b4e2cd0`:
   `git rev-parse next/harness-agnostic` (из основного дерева) и
   `git -C /home/vostrikov/projects/packages/swissknifeman-next rev-parse HEAD`.
4. Пост-мердж валидация В ОСНОВНОМ дереве: пять `packages/{skiller,harness,maind,analyst,task}
   /scripts/validate.sh` + `PYTHONPATH=. python3 -m unittest discover -s core/tests` — все
   зелёные (та же дисциплина, что в P5.1); красный гейт → откат по якорю (шаг 2), не «дочинить
   по месту».
5. Смоук флота НЕМЕДЛЕННО, ПРЕЖНИМ контуром (без префикса PATH к `bin-skm-next`):
   `readlink -f "$(command -v swissknifeman)"` — обязан резолвиться в
   `/home/vostrikov/projects/packages/swissknifeman/bin/swissknifeman`; `swissknifeman doctor`
   — вердикт сверяется построчно с `artifacts/P5.1-fleet-baseline/doctor-before.txt`.
6. Дозаписать в этот раздел (после фактического прогона P5.2): дату, якорь (SHA до merge),
   SHA merge-коммита, число коммитов `main` до/после. → **Выполнено, см. «Факты прогона»
   ниже.**
7. С этого момента рабочий дом плана — ОСНОВНОЕ дерево (D46): P5.2/P5.3 коммитят там; ветка
   `next/harness-agnostic` коммитов больше не принимает и НЕ удаляется (второй якорь отката,
   пока `main` не отправлен наружу).

### Факты прогона P5.2 (заполнено после merge)

| Факт | Значение |
|:--|:--|
| Дата прогона | 2026-07-30 |
| **Якорь отката** (`main` ДО merge) | **`8e16a811`** |
| Коммитов `main` ДО merge | 1473 |
| Слитая ветка (`next/harness-agnostic` HEAD) | `acf73d61` (`acf73d6104c77fd1117ccf5c231134955b4e2cd0`) |
| Ветка впереди `main` на | 102 коммита |
| **SHA merge-коммита** | **`56eae069`** |
| Родители merge-коммита | `8e16a811 acf73d61` (два — не fast-forward) |
| Коммитов `main` ПОСЛЕ merge | 1576 (+103 = 102 ветки + merge) |
| Конфликты | нет (`git merge` exit 0) |
| Пост-мердж валидация | пять `validate.sh` + `core/tests` (251 тест) — все зелёные, python 3.12.3 |
| Смоук ПРЕЖНИМ контуром | `readlink -f "$(command -v swissknifeman)"` → `/home/vostrikov/projects/packages/swissknifeman/bin/swissknifeman`; в `PATH` префикса `bin-skm-next` НЕТ |
| `swissknifeman doctor` vs базлайн | 105/105 строк, вердикт тот же (`Проблем: 2` · `harness: OK` · `Все проверки пройдены.` · `Окружение готово.`); расходятся ДВЕ строки, обе — прямое следствие merge: HEAD `8e16a811`→`56eae069` и sha реестра `041735a37bd6`→`b4675c93e617` (перечень 18 отставших хабов совпадает дословно) |

**Откат** (пока `main` не отправлен наружу): `git -C /home/vostrikov/projects/packages/swissknifeman
reset --hard 8e16a811`. Ветка `next/harness-agnostic` — второй, независимый от reflog якорь.

**Предусловие шага 1 при фактическом прогоне:** `git status --short` основного дерева был
НЕ пуст — три untracked-пути (`.swissknife/` — runtime-состояние analyst; `audits/` — документ
владельца; `packages/task/lib/.claude/` — runtime `runs`/`analyze` со своими `.gitignore`).
Замер показал, что риск R1 («чужая правка попала в merge») не реализуем: tracked-изменений
ноль (`git status --short --untracked-files=no` пусто), и `git diff --stat
main..next/harness-agnostic -- .swissknife audits packages/task/lib/.claude` пусто — ветка эти
пути не трогает, в merge-коммит они не входят. Продолжение — по явному решению владельца
(вопрос задан ДО первой мутации). После merge все три пути на месте, нетронуты.

## Снятие worktree и откат (P5.3, ПОСЛЕДНИЙ шаг — после зелёной дельты)

Порядок необратим по цене, а не по технике (R4): снятие обратимо (процедура «Создание» выше
воспроизводит контур заново), но делать его РАНЬШЕ зелёной дельты превращает откат в ручную
археологию. Предусловие: `artifacts/P5.3-fleet-delta.md` существует, непуст и вердикт по
инварианту М10 зафиксирован; read-only проверка выборки онбордженных проектов пройдена;
коммиты P5.3 сделаны. Снимаемое дерево — НЕ рабочий каталог текущей сессии (D46, п. 7 выше).

```
git worktree remove /home/vostrikov/projects/packages/swissknifeman-next
rm -rf ~/.local/bin-skm-next
```

Откат безопасен: оба шага удаляют только артефакты нового контура, старый контур
(`~/.local/bin` → основное дерево) не затрагивается ни одним из них. Ветка
`next/harness-agnostic` этими командами НЕ удаляется (D46) — проверка:
`git branch --list next/harness-agnostic` непусто и `git worktree list --porcelain` не
содержит записи `/home/vostrikov/projects/packages/swissknifeman-next`.

## Общие поверхности (ОБЩАЯ ПОВЕРХНОСТЬ)

Остаются общими между старым и новым контуром по D4 (изоляция state — Deferred, OQ-5):

- `~/.swissknifeman/topology.json`, `~/.swissknifeman/projects.json`
- `~/.maind/**`
- `.mcp.json` онбордженных проектов (зашитые пути указывают в основное дерево)

Ни один шаг установки нового контура в эти пути не писал (см. проверку mtime ниже).

## Чек «старый контур цел»

Четыре проверки, все зелёные, оба прогона (ДО/ПОСЛЕ установки нового контура) дали
ОДИНАКОВЫЙ результат.

### 1. Резолв симлинков старого контура — ДО и ПОСЛЕ, одинаково

ДО (перед установкой, снимок при старте item'а):
```
$ ls -la ~/.local/bin/{swissknifeman,skiller,harness,maind,analyst}
analyst      -> /home/vostrikov/projects/packages/swissknifeman/packages/analyst/bin/analyst
harness      -> /home/vostrikov/projects/packages/swissknifeman/packages/harness/bin/harness
maind        -> /home/vostrikov/projects/packages/swissknifeman/packages/maind/bin/maind
skiller      -> /home/vostrikov/projects/packages/swissknifeman/packages/skiller/bin/skiller
swissknifeman -> /home/vostrikov/projects/packages/swissknifeman/bin/swissknifeman
```

ПОСЛЕ (`readlink -f` на каждый):
```
/home/vostrikov/projects/packages/swissknifeman/bin/swissknifeman
/home/vostrikov/projects/packages/swissknifeman/packages/skiller/bin/skiller
/home/vostrikov/projects/packages/swissknifeman/packages/harness/bin/harness
/home/vostrikov/projects/packages/swissknifeman/packages/maind/bin/maind
/home/vostrikov/projects/packages/swissknifeman/packages/analyst/bin/analyst
```

Совпадает — старый контур не сдвинулся.

### 2. Резолв CLI нового bin-dir — указывает внутрь worktree

```
$ readlink -f ~/.local/bin-skm-next/{swissknifeman,skiller,harness,maind,analyst}
/home/vostrikov/projects/packages/swissknifeman-next/bin/swissknifeman
/home/vostrikov/projects/packages/swissknifeman-next/packages/skiller/bin/skiller
/home/vostrikov/projects/packages/swissknifeman-next/packages/harness/bin/harness
/home/vostrikov/projects/packages/swissknifeman-next/packages/maind/bin/maind
/home/vostrikov/projects/packages/swissknifeman-next/packages/analyst/bin/analyst
```

Все пять — внутри `swissknifeman-next`, ни один не пересекается со старым деревом.

### 3. Оболочка без префикса PATH выбирает старый CLI

```
$ which swissknifeman
/home/vostrikov/.local/bin/swissknifeman
```

Активация нового контура (`PATH="$HOME/.local/bin-skm-next:$PATH"` в подоболочке)
корректно переключает на новый:
```
$ bash -c 'PATH="$HOME/.local/bin-skm-next:$PATH"; which swissknifeman'
/home/vostrikov/.local/bin-skm-next/swissknifeman
```

### 4. `swissknifeman doctor` через старый контур — тот же вердикт ДО и ПОСЛЕ

ДО (снимок при старте item'а, `/home/vostrikov/.local/bin/swissknifeman doctor`):
```
== harness ==
harness: OK (11 permissions-пресетов, 9 MCP-пресетов, 10 agent-packs, хуки установлены)

== maind ==
[ok] python3 3.12.3 · node в PATH · agentmemory установлен · iii-config.yaml на месте ·
     ~/.maind доступен для записи · конфиг узла валиден
[warn] managed-скиллы: 18 проект(ов) отстали от шаблона
[warn] дубль-канал skiller: 5 проект(ов) раздают скиллы дважды
[ok] пин Serena/схема .serena/project.yml связны
[info] память не запущена
Все проверки пройдены.

== analyst ==
✓ python>=3.8 · core · Окружение готово.
```

ПОСЛЕ (тот же путь, после установки нового контура) — байт-в-байт то же самое: тот же
набор `harness: OK`, те же 2 warn у maind (18/5 проектов), «Все проверки пройдены»,
«Окружение готово» у analyst. Разночтений нет.

### 5. Общие поверхности не сдвинулись

```
$ stat -c '%Y %n' ~/.swissknifeman/topology.json ~/.swissknifeman/projects.json
1783235532 /home/vostrikov/.swissknifeman/topology.json   # 2026-07-05
1785222907 /home/vostrikov/.swissknifeman/projects.json   # 2026-07-28
```

Обе mtime — до сегодняшней установки (2026-07-29): установка нового контура их не
меняла. Единственная запись установки в файловую систему worktree —
`swissknifeman-next/config.json` (создан maind install.sh из example), это
package-local файл, а не общая поверхность из списка выше.

## Вывод

Изоляция воспроизводима (одна команда `install.sh --bin-dir ~/.local/bin-skm-next` из
worktree), обратима (снятие worktree + `rm -rf` bin-dir, без следов в rc-файлах) и не
задела старый контур ни по одной из четырёх проверок и общим поверхностям.
