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

## Снятие worktree и откат (справочно, НЕ выполняется этим item'ом — P5.3)

```
git worktree remove /home/vostrikov/projects/packages/swissknifeman-next
rm -rf ~/.local/bin-skm-next
```

Откат безопасен: оба шага удаляют только артефакты нового контура, старый контур
(`~/.local/bin` → основное дерево) не затрагивается ни одним из них.

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
