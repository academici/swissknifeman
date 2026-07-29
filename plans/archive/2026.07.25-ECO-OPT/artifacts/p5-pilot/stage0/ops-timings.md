# P5.1 — Ops timings (kill-gate)

Измерено на `git worktree`-копии flexcrm (detached HEAD `80182e8f1a30b848c35805ed08a7a206adc17bf7`,
ветка `refactor/vaulter`), CRG `2.3.7` (pipx), эмбеддинги ВЫКЛЮЧЕНЫ (флаги
`--embedding-provider`/`--embedding-model` не передавались — дефолт disabled).

## Полный build

Команда: `/usr/bin/time -v code-review-graph build --repo .`

```
Full build: 405 files, 1235 nodes, 6596 edges (postprocess=full)
Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.66
User time (seconds): 2.66
System time (seconds): 0.37
```

**Ops.build = 1.66 с** — порог D35 `≤ 60 с`: **в пределах** (в ~36× быстрее порога).

## Инкремент после правки одного файла

Правка: одна добавленная строка-комментарий в `app/Models/User.php` (не влияет на семантику).

Команда: `/usr/bin/time -v code-review-graph update --repo .`

```
Incremental: 112 files updated, 9 nodes, 37 edges (postprocess=full)
Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.24
User time (seconds): 0.18
System time (seconds): 0.03
```

**Ops.increment = 0.24 с** — порог D35 `≤ 5 с`: **в пределах**.

**Замеченная аномалия (не порог, но факт для протокола):** `update` без явного `--base`
берёт диф от `HEAD~1` по умолчанию, а НЕ от снимка последнего `build`; при однострочной правке
одного файла инструмент отчитался «112 files updated» — заметно больше, чем ожидалось от
одного изменённого файла. Похоже на побочный эффект пересчёта FTS/постпроцесса по всем файлам
диапазона `HEAD~1..working-tree`, а не баг инкрементальности как таковой (время всё равно
0.24 с, порог не задет) — сырой факт зафиксирован для полноты, дальнейший разбор причины вне
scope ступени 0 (Ops-порог не задет, вердикт не меняется).

## Вывод по числовому правилу (шаг 1 из 3)

`Ops` в пределах обоих порогов D35 ⇒ переход к `P_impact` (шаг 2).
