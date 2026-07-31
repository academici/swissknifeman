# P4 — headless-слой `claude -p` на ЖИВОЙ версии (вход фазы «Драйвер exec-волны»)

**Слой 1 (сырьё).** Замер выполнен 2026-07-31 в этом репозитории; метод — прямой прогон
установленного CLI, не чтение документации. Назначение: пере-снять транспортный слой, на
котором стоит фаза P4, потому что историчный parse-контракт донора
(`plans/archive/2026.07.18-FOREMAN/root/contracts/driver-plan-protocol.md`) запинен на
2026-07-18 и объявлен ИСТОРИЧЕСКИМ (его §0), а его §2 описывает конверт полутора-месячной
давности.

## 0. Версия и метод

- `claude --version` → **`2.1.220 (Claude Code)`**.
- Метод: (а) полный дамп `claude --help` (230 строк) с поиском по флагам; (б) два реальных
  прогона `claude -p … --output-format json` с разбором конверта.
- Прогон 1: cwd — временный каталог сессии, промпт `Reply with exactly: ok`.
- Прогон 2: cwd — корень репозитория, промпт `/core:compact-responses` (слэш-команда
  плагина, побочных эффектов не несёт).

## 1. Флаги, релевантные драйверу (по `claude --help` 2.1.220)

**Есть:**

| Флаг | Что даёт драйверу |
|:--|:--|
| `-p, --print` | неинтерактивный прогон (диалог доверия к workspace пропускается) |
| `--output-format <text\|json\|stream-json>` | машинный конверт исхода |
| `--model <model>` | селектор модели (алиас `opus`/`sonnet`/`fable` либо полное имя) |
| `--effort <level>` | `low, medium, high, xhigh, max` — селектор effort'а сессии |
| `--session-id <uuid>` | принудительный id сессии (линковка с журналом) |
| `--permission-mode <mode>` | `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan` |
| `--add-dir`, `--allowedTools`, `--disallowedTools`, `--settings`, `--agents` | сужение поверхности прогона |
| `--append-system-prompt` | инъекция текста в системный промпт (приём `quality/eval.py`) |
| `--fallback-model <list>` | авто-фолбэк при перегрузе/недоступности (работает только с `--print`) |
| `--disable-slash-commands` | «Disable all skills» — то есть по умолчанию скиллы/слэш-команды в `-p` РАБОТАЮТ |
| `--bare` | минимальный режим: без хуков, LSP, plugin sync, авто-памяти и авто-обнаружения `CLAUDE.md` |

**НЕТ:** `--max-turns` — в помощи 2.1.220 **ноль совпадений** по строке `max-turns`
(поиск по всем 230 строкам). Историчный контракт донора §2 утверждал «число ходов (лимит
`--max-turns`, D7 — флаг работает)»; на живой версии это утверждение **не воспроизводится**
и наследоваться в переизданный контракт не должно. Ограничение длины прогона остаётся за
таймаутом процесса.

## 2. JSON-конверт `--output-format json` — живой снимок

Полный набор ключей верхнего уровня (прогон 1, дословно):

```text
api_error_status · duration_api_ms · duration_ms · fast_mode_disabled_reason ·
fast_mode_state · is_error · modelUsage · num_turns · permission_denials · result ·
session_id · stop_reason · subtype · terminal_reason · time_to_request_ms ·
total_cost_usd · ttft_ms · ttft_stream_ms · type · usage · uuid
```

Значения успешного прогона 1:

```text
type=result · subtype=success · is_error=False · stop_reason=end_turn ·
terminal_reason=completed · num_turns=1 · total_cost_usd=0.08049650 ·
session_id=7c572e2f-fc29-4ce8-96dc-92764c4d99ee · duration_ms=2065 · api_error_status=None
```

**Что изменилось против историчного контракта донора (§2, 2026-07-18).** Тогда читаемыми
объявлялись `type`, `is_error`, `result`, `session_id`, `total_cost_usd`, `num_turns`,
`duration_ms` — все семь на месте. Добавились поля, прямо полезные вердиктному гейту и в
контракте донора отсутствующие:

- `subtype` (`success` на удачном прогоне) — второй, более узкий признак исхода;
- `stop_reason` (`end_turn`) — причина остановки модели;
- `terminal_reason` (`completed`) — причина завершения сессии;
- `api_error_status` (`None`) — транспортный статус ошибки API;
- `permission_denials` (список) — отказы разрешений: прямой сигнал «прогон упёрся в
  политику, а не в задачу»;
- `uuid`, `ttft_ms`, `ttft_stream_ms`, `time_to_request_ms`, `duration_api_ms`,
  `fast_mode_state`, `fast_mode_disabled_reason` — телеметрия.

## 3. Слэш-команда через `-p` — проверено прогоном, не доком

Прогон 2 (`claude -p '/core:compact-responses' --output-format json`, cwd — корень репо):

```text
is_error=False · subtype=success · stop_reason=end_turn · terminal_reason=completed ·
num_turns=1 · total_cost_usd=0.16505 · exit=0 · result='Compact mode active.'
```

Скилл плагина, вызванный слэш-формой, **отработал** — то есть несущее допущение фазы P4
(«воркер запускается как `claude -p "/task:plan-exec <ID> <item>"`») на живой версии
подтверждено наблюдением. Косвенные подтверждения из помощи: `--disable-slash-commands`
существует как ОТКЛЮЧЕНИЕ (значит по умолчанию включено), а описание `--bare` прямо
говорит «Skills still resolve via `/skill-name`».

## 4. Что НЕ измерено этим заходом (границы честности)

- **Конверт при исчерпании квоты.** Историчный контракт (D18 донора) описывал `is_error=true`
  + exit 1 + различение по ТЕКСТУ `result` (`session limit` / `weekly limit`) и отсутствие
  reset-timestamp. На 2.1.220 появилось поле `api_error_status`, и вероятно `terminal_reason`
  тоже несёт класс — **не проверено** (воспроизвести исчерпание квоты намеренно этот заход
  не мог). Класс — `[UNVERIFIED]`, адрес — P4.1 (фиксирует как открытый пункт контракта) и
  P4.3 (дефенсивный разбор обязан не падать на неизвестном сочетании).
- **Exit-коды на сбоях** (таймаут, битый конверт, отказ разрешений) — наблюдался только
  `exit=0` на успехе. `[UNVERIFIED]`.
- **Совместимость `--effort` с `-p`.** Флаг заявлен как «for the current session»;
  раздельного подтверждения, что он применяется в неинтерактивном прогоне, замер не даёт.
  `[UNVERIFIED]`, адрес — P4.3 (проверяется на фикстуре при сборке argv).
- **Стоимость прогона.** Два тривиальных прогона обошлись в `0.080` и `0.165` USD — это
  порядок «служебного» вызова; экономика волны меряется P4.6, а не экстраполируется отсюда.

## 5. Следствия для фазы

1. **P4.1** переиздаёт §JSON-конверта по разделу 2 этого файла, а не по донору; строка про
   `--max-turns` в переизданный контракт не попадает (раздел 1); незакрытые пункты раздела 4
   входят в контракт как явные `[UNVERIFIED]`, а не как умолчания.
2. **P4.3** разбирает конверт дефенсивно по полям `type`/`subtype`/`is_error`/`stop_reason`/
   `terminal_reason`/`api_error_status`/`permission_denials` + exit code; ограничение длины
   прогона — таймаут процесса (флага `--max-turns` нет).
3. **P4.4** получает два новых признака для вердикта: непустой `permission_denials` →
   `ATTENTION` (прогон упёрся в политику), `api_error_status`/`terminal_reason` ≠ штатных →
   класс транспортного/квотного сбоя → `RED` + пауза волны (ретрая нет, D9).
4. **Правило внешних фактов плана** (`plan.md` §2) соблюдено: всё, что здесь утверждается о
   поведении Claude Code, получено прогоном на 2.1.220 и несёт команду воспроизведения.
