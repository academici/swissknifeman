# Идея: разделы аудита `skm-ench.md`, оставленные вне PLAN6

Статус: идея, не реализовано. Источник: аудит владельца `skm-ench.md`, сверенный с кодом HEAD `666f89b67` при проектировании
PLAN6 (knowledge `audit-verification`, решение D11). План переносит планы в portable workspace
(ADR 0085); перечисленное ниже от переноса не зависит, поэтому в план не вошло. Каждый раздел ждёт своего триггера; пока
триггера нет, ничего из этого не строится (правило «не строить спекулятивную машинерию», `planner-development-philosophy`).

Prompt profiles в этот список не входят: они запланированы в PLAN4 P13.3.

## Оркестратор: политика progress lines и остаток раздела conductor

**Факт.** Строки прогресса `[orch] <item> <step> <what>` требуются ролям безусловно: `packages/orch/lib/orch/conductor/prompts.py`
(строка 6) и `packages/orch/docs/conductor.md`. Аудит это подтвердил.

**Что может понадобиться.**
- политика progress lines по провайдеру и роли (кому нужны, кому мешают);
- typed scout result вместо свободного текста;
- `ContextPack/v1` как единый контракт контекста, который получает роль;
- diff chunking для ревью больших диффов;
- fast-check gate перед ревью (дешёвая проверка, после которой ревью не тратится на заведомо красный дифф);
- context-effectiveness telemetry (какая часть переданного контекста реально использована);
- model fallback policy (когда и на какую модель падать при отказе провайдера).

**Триггер.** Политика progress lines — после PLAN4 P13.3 (профили промптов, тогда видно, что остаётся общим). Остальное — по
одному, когда отчёт observer или журнал запусков conductor покажет повторяющуюся потерю (перерасход токенов, ревью красного
диффа, срыв по лимиту провайдера) именно в этом месте.

## Skills: manifest v2, lint, конфликты, оценка

**Что может понадобиться.** `skill/v2` manifest; команды skiller `lint-modern`, `conflicts`, `eval-benefit`,
`eval-cross-provider`, `explain-instructions`, `retire-candidates`; жизненный цикл skill `draft → archived`.

**Факт.** `packages/skiller/lib/skiller/quality/analyze.py` сам помечает вердикт DEAD как эвристику (строка 12): автоматическое
`retire-candidates` на этой основе давало бы ложные удаления, пока нет измерения пользы.

**Триггер.** Появляется измеримая оценка пользы skill (`eval-benefit` на реальных запусках) либо владелец сообщает о
конфликте двух skills в одном проекте, который `skiller select` не разрешил. До этого `skill-selection/v1` достаточно.

## Workspace: что отложено после первой версии

**Что может понадобиться.**
- фоновые режимы sync: on-change, scheduled, on-exit;
- per-device immutable event journal вместо одного общего `log.jsonl`;
- semantic merge UI по полям документов плана;
- advisory run claims между машинами (кто сейчас ведёт план);
- coordination backend;
- selective project sync (синхронизировать не все проекты);
- encrypted materials (шифрованные материалы в workspace);
- multi-user.

**Почему отложено.** PLAN6 даёт ручной `workspace sync` с merge по строкам (`log.jsonl merge=union`) для одного владельца и
двух машин. Остальное решает проблемы, которых при этом режиме ещё нет.

**Триггер.**
- фоновый sync — владелец дважды забыл выполнить `workspace sync` и потерял работу между машинами или получил
  `WORKSPACE_BEHIND` в середине сессии;
- per-device journal и semantic merge — `WORKSPACE_CONFLICT` на документах плана чаще раза в месяц;
- run claims и coordination backend — два одновременных запуска одного плана на разных машинах хотя бы раз;
- selective sync — workspace перестаёт помещаться на вторую машину;
- encrypted materials и multi-user — запрос владельца (появляется второй человек или секретные материалы).

## Plan materials manifest с `load_policy`

**Что может понадобиться.** Манифест материалов плана с политикой загрузки: `always`, `for-role`, `for-item`, `on-demand`,
`human-only`, `archived`.

**Факт.** Сейчас эту роль выполняют чтения секций `knowledge/<id>#<section>` в пунктах и `context_pack: scoped`.

**Триггер.** Измеренный перерасход токенов контекста из-за материалов: раздел, который роль получила и не использовала, в
нескольких запусках подряд.

## Standalone tasks inbox с `promoted_to`

**Что может понадобиться.** Входящие задачи вне плана, у которых после разбора появляется ссылка `promoted_to` на пункт плана.

**Триггер.** Запрос владельца. Сегодня для этого используются `ideas/` и plan notes.

## Остаток config UX

**Что может понадобиться.** Ключи в схемах конфигурации `restart_required`, `portable`, `provider_specific`, `ui.control`;
запрет machine-путей в project-слое конфигурации.

**Триггер.** Страница Settings в GUI начинает показывать настройки, которые требуют перезапуска, или в коммит попадает
project-слой с абсолютным путём машины (`maind doctor --gitignore-drift` это уже ловит для известных файлов; запрет в схеме
нужен, когда появится путь вне этого списка).

## Не относится к ideas

Устаревшая строка статуса `packages/gui/README.md` («desktop and sidecar are the target layout») при существующих
`packages/gui/desktop` и `packages/gui/sidecar` правится в PLAN6 P5.2, где этот README затрагивается.
