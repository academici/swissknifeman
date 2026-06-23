# review-gate — гейт соблюдения архитектуры (SubagentStop)

Детерминированный L5-рубеж: после завершения субагента прогоняет настроенную
проектом проверку и, если она не прошла, подсказывает (или блокирует). Дополняет
`skills:`-preload skiller (L2): preload даёт агенту скиллы, гейт ловит то, на что
агент всё равно забил — гарантия там, где проза «следуй скиллу» её не даёт.

## Режимы (`env.ini`, дефолт `warn`)

| MODE | Поведение при провале проверки |
|---|---|
| `off` | ничего |
| `warn` | подсказка в контекст (`additionalContext`), субагент НЕ блокируется |
| `strict` | блок субагента (`exit 2` + причина) |

Per-project: `.claude/review-gate.env.ini` (`MODE=...`).

## Проверка (`config.json` → `check_command`)

Без `check_command` хук — **no-op** (безопасный дефолт). Проект включает гейт,
задав команду в `.claude/review-gate.config.json`:

```json
{ "check_command": "<shell; exit 0 = чисто, ≠0 = нарушение; stdout → подсказка>" }
```

Команда выполняется в каталоге проекта (`cwd` из payload хука).

### Пример (Laravel — запрет прямого Eloquent в контроллерах)

```json
{
  "check_command": "git diff --name-only -- app/Http/Controllers | xargs -r grep -nE '::(query|create|where|all|find)\\(' && exit 1 || exit 0"
}
```

Если субагент оставил в контроллере `Model::query()/::create()` — в `warn` придёт
подсказка с file:line, в `strict` субагент будет заблокирован до исправления.

## Проводка

Хук висит на событии `SubagentStop` в `settings.global.json`. Файлы ставит
`harness hooks --global` (`apply-permissions.sh`) в `~/.claude/hooks/review-gate/`.

## Проверка после установки (live)

`exit 2`-блок и `additionalContext` подтверждаются только реальным прогоном
субагента: задать `check_command`, который заведомо падает, и убедиться, что в
`warn` приходит подсказка, а в `strict` субагент блокируется.
