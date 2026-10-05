# Журнал запросов Perplexity

Дата: 2026-10-05. Использован существующий локальный `perplexity-web-mcp`: daemon dispatcher и браузерный default pool. Это реальные запросы к Perplexity через браузерный backend, не имитация ответа нашей моделью. API key не использовался; credentials, cookie и auth state в пакет исследования не включены.

Вопросы описывали **обобщённую** систему: локальный Python monorepo, JSON plan manager, reusable skills, environment installer и ранний runtime. Perplexity не получал private source files и от него не требовалось знание Swiss Knife Man. Repo-specific выводы сделаны отдельной проверкой местного кода.

## Точные запросы и полученные результаты

Все запросы: [queries.json](perplexity/queries.json). У каждого вызова сохранены query, начало/завершение и неизменённый объект результата в JSON; Markdown — читабельное представление этого объекта. Время — UTC.

| ID | Тема | Результат | Structured sources | Как использован |
| --- | --- | --- | ---: | --- |
| Q01 | CAO features, version, maturity | [JSON](perplexity/Q01.json), [ответ](perplexity/Q01.md) | 10 | Discovery маршрутов/docs; сверено по CAO code |
| Q02 | Свой runtime против CAO | [JSON](perplexity/Q02.json), [ответ](perplexity/Q02.md) | 3 | Список tradeoffs; вывод уточнён после repo audit |
| Q03 | Классификация исходных кандидатов | [JSON](perplexity/Q03.json), [ответ](perplexity/Q03.md) | 10 | Навигация по проектам; Vercel/Pydantic перепроверены отдельно |
| Q04 | Экономика большого context pipeline | [JSON](perplexity/Q04.json), [ответ](perplexity/Q04.md) | 0 | **Пустой answer**; не засчитан как исследование, повторён Q04b |
| Q05 | Универсальность skills/commands/engines | [JSON](perplexity/Q05.json), [ответ](perplexity/Q05.md) | 8 | Основа вопросов ownership/capabilities; местная SSOT проверена кодом |
| Q06 | Resume и side effects | [JSON](perplexity/Q06.json), [ответ](perplexity/Q06.md) | 2 | Проверены shim, authoring guide и journal |
| Q07 | Model/effort/auth/permissions | [JSON](perplexity/Q07.json), [ответ](perplexity/Q07.md) | 3 | Есть неверный Claude effort claim; исправлен code review |
| Q08 | Критика CAO и failure cases | [JSON](perplexity/Q08.json), [ответ](perplexity/Q08.md) | 0 | Есть устаревший Python resume claim; отдельные ссылки только внутри текста |
| Q04b | Повтор экономики после пустого Q04 | [JSON](perplexity/Q04b.json), [ответ](perplexity/Q04b.md) | 3 | Формула/measurement; конкретные cache rates не приняты как основание решения |
| Q09 | Structured interfaces против TUI | [JSON](perplexity/Q09.json), [ответ](perplexity/Q09.md) | 0 | Discovery, затем самостоятельная проверка официальных Claude/Codex/Grok docs |
| Q10 | Повторное сравнение с новым Vercel HarnessAgent/Grok ACP | [JSON](perplexity/Q10.json), [ответ](perplexity/Q10.md) | 6 | Подтвердил необходимость пересмотра API-only классификации; packages проверены npm/GitHub |

Итого: **11 вызовов, 10 непустых answer**, один пустой вызов сохранён и повторён. Непустой ответ не означает правильный вывод; количество источников не означает, что каждый поддерживает каждый claim.

## Ограничения сохранённого материала

JSON сохраняет то, что вернул браузерный текстовый extractor. Это не полный HTML/export Perplexity UI: inline citation anchors и таблицы могут потеряться. Например, Q10 вернул пустой блок «Сравнение», Q08/Q09 — пустой structured source list при наличии текста. Пропущенное содержимое не дорисовано и не выдано за полученный ответ. Для выводов использованы отдельно открытые primary docs/source.

Списки sources сохранены такими, как их вернул сервис. Формулировка `primary-source URLs` в запросе сама по себе не гарантирует, что ответ использовал первичные источники или корректно их интерпретировал.

## Контрпроверка важных утверждений

| Claim из Perplexity | Что показала независимая проверка | Где исправлено |
| --- | --- | --- |
| Q07: нет Claude effort в CAO | Есть `claudeConfig.effort` и launch flag в main и исследованном tag | [CAO audit](../audit-amazon-cao.md) |
| Q08: Python completed steps при resume не replay | Shim/server умеют replay; script исполняется сверху, agent step может не запускаться | [CAO audit](../audit-amazon-cao.md) |
| Q03/исходный диалог: Vercel главным образом API SDK | В актуальном наборе есть experimental HarnessAgent и опубликованные native runtime adapters | [Alternatives](../alternatives.md) |
| Q07 использует имя `grok_build` | Реальный CAO provider ID — `grok_cli`; mapping нужен явно | [CAO audit](../audit-amazon-cao.md) |
| Skills scope означает ограничение всех доступных skills | В CAO это advertised catalog, не универсальная ACL | [CAO skills](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/skills.md) |
| Journal orphan fallback не имеет terminal ID | Schema уже имеет поле; конкретный begin-step script path не сохраняет его в running window | [CAO audit](../audit-amazon-cao.md) |
| Подписочные CLI автоматически дешевле API и совместимы с любым wrapper | Entitlement, auth route и quota конкретного аккаунта не проверены | [Economics](../model-economics.md), [pilot](../pilot-and-claude-handoff.md) |

Слабые места исходного пользовательского диалога также разобраны в [repository audit](../repository-audit.md). Его текст не редактировался.

## Как повторить исследование

1. Использовать доступный Perplexity connector либо существующий локальный browser service; обеспечить его обычную авторизацию вне artifacts.
2. Взять точный `query` нужного ID из queries.json и сохранить returned answer/sources с timestamp.
3. Проверить пустые answers и отсутствие источников; не выдавать degraded extraction за полное исследование.
4. Открыть первичные источники, зафиксировать release/commit и проверить изменчивые claims в actual code.
5. Сохранить новые результаты с новыми IDs, не переписывать исторические raw ответы.

Локальный transport сам по себе не часть предлагаемого orchestration runtime. Его исходники в этом исследовании не менялись и новая Perplexity-интеграция в Swiss Knife Man не добавлялась.
