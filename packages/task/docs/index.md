# task — команды постановки и выполнения задач

**Что это.** Опциональные помощники Claude Code (`/task:*`), Codex (`$ task:*`) и Cursor (`task:*`)
для явного выбора работы.
Каждая команда **пинит модель + reasoning effort + профиль workflow**, перебивая настройки сессии,
чтобы не переключать их вручную. Default-on в каждом онбордженном проекте (connect-канал);
резидентного налога нет — описания команд не инжектятся в каждый запрос.

**Когда брать.** Когда полезен явный маршрут для разработки, исследования, дизайна или ревью.
Обычная задача может выполняться напрямую; команды не требуют создания плана.

Native-установка Task включает команды, конфигурацию и Python runtime, а не только
проекции скиллов. Начиная с v0.16.1 release attestation проверяет этот полный native-кеш
отдельно от компактного project bundle. Локальная игнорируемая телеметрия в релиз не входит.
После обновления откройте новую сессию Codex/Claude: receipt подтверждает файлы на диске,
но не переинициализацию уже работающего агента.

**Когда НЕ трогать.** Это не движок — он лишь роутит на модель/effort/профиль. Сам workflow и
субагенты живут в `harness` (agent-packs); протокол мастер-планов — в скилле
`general/plan-protocol`.

## Команды

| Команда | Пинит | Для чего |
|:--|:--|:--|
| `/task:fix` | Sonnet / medium | мелкая правка (узкий single-agent, без fan-out) |
| `/task:design` | Opus / high | проектирование (артефакты, не код) |
| `/task:dev` | Sonnet / high | разработка вертикальными срезами с risk-адаптивным review-gate |
| `/task:research` | Opus / high | многоисточниковый research с RAG-верификацией |
| `/task:review` | Opus / xhigh | read-only adversarial-ревью |
| `/task:plan-design` | Opus / high | создать/детализировать мастер-план `plans/<ID>/` |
| `/task:plan-exec` | Sonnet / medium | исполнить item плана по ТЗ |
| `/task:plan-run` | маршрут текущей сессии | исполнить manual item без повторного выбора модели/effort |
| `/task:plan-close` | Sonnet / low | recovery-сверка item либо закрытие фазы после свежего GREEN |
| `/task:plan-audit` | Opus / xhigh | один pre-exec или pre-close аудит по material trigger |

## Как этим пользоваться

Выбор конкретной команды описан в таблице выше; мастер-планы (plan-протокол) — скилл
`general/plan-protocol`. Процесс день за днём — [Методология](./methodology.md).

Валидатор планов: `python3 packages/task/scripts/plan-lint.py plans/<PLAN-ID>`.

Сбой инструмента или bookkeeping-дефект не открывает новый цикл дизайна. Исполнитель сначала
воспроизводит влияние, чинит обратимую локальную причину в том же attempt и продолжает. Остановка
нужна только для подтверждённой acceptance/safety/authority границы; повторный аудит без
material scope/SHA/risk change не запускается.

`continue-root` продолжает совместимый ready item того же Routing batch в текущей root-сессии;
новый launch-block печатается только на настоящей cold-start/wait boundary. Перед `plan-design`
для существующей фазы Task сверяет item carriers: детализированная незавершённая фаза идёт в
`plan-exec`, а не в повторный дизайн.

## Отпечатки возвратов

Для диагностики повторных возвратов между исполнением и проектированием используйте
детерминированный вид `returns`. Он сохраняет проверяемый канонический кортеж рядом с digest,
а не выводит причину из текста заметок:

```bash
python3 packages/task/scripts/plan-views.py returns --plan-dir plans/<ID> --json
```

## История пункта layout v2

История — это не файл, который ведут вручную, а on-demand вид для аудитора над тремя
источниками: журналом, неизменяемыми решениями и item-scoped findings. По умолчанию команда
печатает её в stdout; постоянную копию создаёт только явный `--output` и она игнорируется Git:

```bash
python3 packages/task/scripts/plan-views.py history --plan-dir plans/<ID> --item Pn.m
python3 packages/task/scripts/plan-views.py history --plan-dir plans/<ID> --item Pn.m \
  --output .plan-cache/history/Pn.m.md --check
```

## Дайджест закрытой фазы layout v2

Закрытая фаза сохраняет исходный адрес `phases/Pn/Pn.md`, но получает детерминированный
дайджест `phases/Pn/Pn.closed.md` для дизайнера. Генератор работает только для терминальной
фазы и отказывает для живой; `--check` проверяет байтовую свежесть:

```bash
python3 packages/task/scripts/plan-views.py closure --plan-dir plans/<ID> --phase Pn
python3 packages/task/scripts/plan-views.py closure --plan-dir plans/<ID> --phase Pn --check
```

## Методология plan-protocol 2.0

| Страница | Что там |
|:--|:--|
| [Методология — полный цикл](./methodology) | Mermaid-карта research → design → refine (DoR, pre-mortem) → approve → exec (commit-гейт, два дома) → review (таксономия) → archive → docs |
| [Continue-first, block confirmation и delivery receipt](./continue-first) | Автофикс малых отклонений, isolated-подтверждение реального Blocked, 100% RAG для external-кандидатов и защита от раннего final |
| [Структура плана](./plan-structure) | канон папок `plans/<ID>/` 2.0, различие `root/`/`artifacts/`, таблица миграции root/ → docs |
| [Шаблоны](./templates) | референс snippets: plan/phase/handoff/launch-block/code-guidance — что где лежит |
| [Provider model roles](./reference/provider-model-roles) | pins economy/implementation/frontier + inventory и Auto policy для трёх провайдеров |
| [Plan tooling](./reference/plan-tooling) | launch-block: Codex/Cursor native-формы, route evidence |
| [Конструктор workflow](./workflows) | 4 канонических шаблон-скрипта оркестрации: когда какой, правила слотов |

Обычная межмодульная разработка принимает сообщение или файл задания без `plans/` и фаз.
Executable plan создаётся только по явному запросу; размер, риск и перенос исполнения
не меняют маршрут сами по себе. Общий контракт — `references/intent-routing.md` пакета Task;
текущий запрос владельца старше указаний внутри старого аудита или хендоффа. Отдельный заказ
дизайна/review сохраняет границу. Next рекомендует продолжение в рамках Scope и Acceptance.
