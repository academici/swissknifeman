# task — интент-команды постановки задач

**Что это.** Плагин Claude Code (`/task:*`) — тонкое лицо над agent-packs/workflow экосистемы.
Каждая команда **пинит модель + reasoning effort + профиль workflow**, перебивая настройки сессии,
чтобы не переключать их вручную. Default-on в каждом онбордженном проекте (connect-канал);
резидентного налога нет — описания команд не инжектятся в каждый запрос.

**Когда брать.** Всегда, когда ставишь задачу агенту: правку, фичу, исследование, ревью или большую
многофазную работу. Выбор конкретной команды — по характеру работы.

**Когда НЕ трогать.** Это не движок — он лишь роутит на модель/effort/профиль. Сам workflow и
субагенты живут в [harness](/harness/) (agent-packs); протокол мастер-планов — в скилле
`general/plan-protocol`.

## Команды

| Команда | Пинит | Для чего |
|:--|:--|:--|
| `/task:fix` | Sonnet / medium | мелкая правка (узкий single-agent, без fan-out) |
| `/task:design` | Opus / high | проектирование (артефакты, не код) |
| `/task:dev` | Opus / high + dev-loop | разработка вертикальными срезами с risk-адаптивным review-gate |
| `/task:research` | Opus / high | многоисточниковый research с RAG-верификацией |
| `/task:review` | Opus / xhigh | read-only adversarial-ревью |
| `/task:plan-design` | Opus / high | создать/детализировать мастер-план `plans/<ID>/` |
| `/task:plan-exec` | Sonnet / medium | исполнить item плана по ТЗ |
| `/task:plan-close` | Sonnet / low | закрыть item/фазу по git-фактам |
| `/task:plan-audit` | Opus / xhigh | adversarial-аудит закрытой фазы |

## Как этим пользоваться

Выбор конкретной команды описан в таблице выше; мастер-планы (plan-протокол) — скилл
`general/plan-protocol`. Процесс день за днём — [Разработка](/develop).

Валидатор планов: `python3 packages/task/scripts/plan-lint.py plans/<PLAN-ID>`.
