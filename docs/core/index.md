# core — общий фундамент пакетов

**Что это.** stdlib-only пакет-фундамент монорепо: единый источник истины для примитивов, которые
пакеты (`skiller`/`harness`/`maind`/`analyst`) исторически копировали независимо. Подключается через
PYTHONPATH (без pip); `Env` каждого пакета наследует `core.BaseEnv`, импорт — `from core import …`.

**Когда трогать.** Когда примитив дублируется между ≥2 пакетами со стабильной границей — его место
здесь, а не параллельные копии. Доменные надстройки (path-property `Env` каждого пакета) остаются в
`common.py` пакетов — они расходятся по контракту.

## Что внутри

| Модуль | Даёт |
|:--|:--|
| `term` | `die` · `warn` · `confirm` · `now_iso` · `parse_iso` |
| `text` | `parse_frontmatter` · `parse_inline_list` · `sanitize` (slug) |
| `env` | `BaseEnv` (frozen-dataclass ядро root/cmd/home) · `HOME` |
| `io` | `atomic_write_text/json` (tmp+`os.replace`) · `safe_load_json` · `load_json_db` · `read_ndjson` · **`backup_file`** |
| `repo` | `find_repo_root` · `find_monorepo_root` · **`sibling_bin`** (резолвер лаунчера соседа) |
| `block` | управляемый markdown-блок: `managed_block` · `upsert_block` · `content_hash` |
| `http` | urllib-клиент: `http_get_json` · `http_post_json` · `ping` |
| `cli` | `parse_flags` · `parse_args` · `run_cmd` (guarded subprocess) |
| `paths` | `is_within` · `is_within_lexical` · `state_dir` |
| `project` | `PROJECT_TYPES` · `detect_project_type` · docs-visibility |
| `pathology` | `detect` — детектор «патологий» прогона (общий для `maind analyze` и `analyst digest`) |
| `usage` | аккумулятор токенов/usage прогона (`new_acc`/`feed_event`/`finish`) |
| `proc` · `runs` | `pid_alive` · `find_run_report` |

## Reference: телеметрия прогона (SCHEMA=2)

`core/usage.py` — единый аккумулятор токенов, на который опирается вся телеметрия. Захват прогона
делает SessionEnd-хук harness (`hooks/run-report/`): строчно парсит транскрипт → пишет
`<project>/.claude/runs/<sid>.json` (**SCHEMA=2**: тесты/линт/файлы/tool-провалы/dev-loop-сигнал +
usage-партиция in/out по модели). Этот run-report читают:

- **`maind analyze`** — пост-ран вердикт GREEN/ATTENTION/RED (дёргал ли агент память/граф);
- **`analyst token-report`** — usage-trend + rolling-baseline (`.claude/analyze/baseline.json`);
- **`core.pathology.detect`** — детектор рецидивных патологий (правило ≥2/5 по истории run-report).

Операционный слой этого — [Разработка §9](/develop#_9-измерение-эффективности-★).

## Разработка

```bash
PYTHONPATH=. python3 -m unittest discover -s core/tests   # smoke-тесты core
```
