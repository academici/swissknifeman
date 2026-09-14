# Реализация аудита: результат и проверенные границы

Дата: 2026-09-14. Исполнитель: Astra в текущем root; самостоятельные части и независимое
ревью выполнены помощниками. Sol не понадобился: сохранён собранный контекст.
Авторизация: последующее поручение владельца «ну выполняй тогда».

## Измеренный результат

`codex-cli 0.154.0 debug prompt-input` воспроизводит фактический стартовый prompt без
отправки запроса модели. Для каждого cwd проверены `gpt-6-astra` и `gpt-5.6-sol`,
`-a never`, `-s danger-full-access`. Результаты обоих маршрутов совпадают.

| Проект | Видимых скиллов до → после | Сокращённых descriptions до → после | Символов полного prompt до → после |
|---|---:|---:|---:|
| Edufy | 102 → 61 | 90 → 0 | 49 355 → 24 871 |
| Flexcrm | 136 → 94 | 136 → 0 | 47 930 → 47 455 |
| CoreX | 190 → 77 | 190 → 0 | 32 971 → 31 848 |

Это символы и metadata discovery, не provider token usage. Освобождённое место позволяет
сохранить полные описания; поэтому уменьшение количества скиллов не обязано давать такое
же относительное уменьшение prompt. В Flexcrm остаются полезные Nuxt/Filament и локальные
версионные знания. Их наличие подтверждено вложенными package manifests и composer.json.

Доказательства: [runtime-before.json](runtime-before.json), [runtime-final.json](runtime-final.json),
[measure-runtime.py](measure-runtime.py). Промежуточные snapshots сохранены для диагностики.
Предупреждение не воспроизводится по признаку сокращённых descriptions в финальном native
prompt. Уже открытые сессии не переизмерялись и не считаются автоматически обновлёнными.

## Что изменено

- CORE: четыре identity — anti-drift, context-economy, session-handoff, verify-claims.
  Остальные исходники сохранены. Plan protocol доступен по необходимости из Task runtime.
- Проверены 78 daily identities; 66 descriptions сокращены: 15 593 → 5 847 символов.
  Все 11 Task descriptions имеют отдельные короткие триггеры. VueUse entry сокращён
  с 3 675 до 272 слов, все 276 каталоговых строк сохранены в reference.
- Переписаны конфликтные правила anti-drift, TDD, review/testing, package contribution,
  PHP architecture и SSOT. Авторизация не запрашивается повторно; принятые project
  contracts отделены от универсальных советов. Изоляция, authority и ownership сохранены.
- `skiller connect --native-codex` записывает точную native plugin selection проекта,
  включая false для невыбранных унаследованных плагинов. Глобальные enable/disable defaults
  сохранены. Permissions не меняются этим режимом, неизвестные TOML-поля сохраняются.
- `--hub` генерирует AGENTS после native selection; Codex fallback содержит только его
  выбранные плагины и declared local skills. Claude-only extras не возвращаются в AGENTS.
- CoreX: 65 идентичных managed links заменены native-поставкой; ещё 16 явно отключённых
  environment links архивированы. Два preflight скилла и уникальные локальные скиллы сохранены.
  Пять уже недействительных ссылок на бывшие CORE carriers не участвуют в discovery;
  их marker сохраняется как след прежней поставки. Никакие canonical знания не удалены.
- Flexcrm: архивирована одна физическая дублирующая Laravel best-practices копия;
  native PHP skill сохранён. Исправлены источники и manual projections стека, оркестратор,
  skills-ssot, документация source-layout. Из composer post-update удалён только неработающий
  Boost update hook. Пользовательское удаление boost.json сохранено.
- mAInd: укорочены два template descriptions, owning CLI обновил 12 provider copies в трёх
  проектах. Тела и подстановки не изменены. Четыре локальных Flexcrm Boost descriptions
  сокращены отдельно, с backup и сохранением тел; dependencies не редактировались.
- Личные owner-autonomy/find-skills: убран обход audit cap через новый план и слишком широкий
  триггер поиска скиллов на обычную просьбу реализовать функцию.

Новые бакеты не создавались: измеренный перебор устранён выбором существующих пакетов,
дедупликацией и metadata diet. Предложения более мелкого разбиения остаются условными
рекомендациями матрицы, а не обязательной новой архитектурой.

## Task и сегодняшние roadmap

| Carrier | Реализовано | Остаток |
|---|---|---|
| plan-run alias | Общий resolver нормализует alias к существующему manual owner route; raw command и route evidence сохранены. Lint/build/adapters проверены. | Carrier архивирован. |
| Owner continuity | Завершение заказанного scope в чате отличается от явно запрошенной новой сессии; Next строится из актуального состояния. | Полевой прогон двух соседних items в рабочем проекте. |
| Dirty worktree | Убрано clean-tree требование fix; baseline/semantic composition сохранены. Сам факт dirty path не выдаёт owner gate. | Полевой replay конкретного Edufy инцидента. |
| Terminal emission | Общий `plan-delivery --render-final` работает без optional lease и валидирует receipt; guidance использует его для финального фрагмента. | Это не универсальный перехват фактического provider final. Без admission hook нельзя технически гарантировать, что модель не проигнорирует Next. |
| Unicode bundle | Существующий repair и authority guard сохранены; native Task runtime содержит их байты. Regression tests входят в qualification. | Реальное CoreX P3.1 остаётся за своим CONSUMER-DOMAIN gate; audit не выдаёт consumer authority и не генерирует business binding. Tagged release не выпускался. |

Task runtime теперь несёт 15 вспомогательных файлов references/snippets. Relocation test
проверяет их без Skiller checkout. В двух шаблонах снята зависимость от Claude-only env.
Выявлен и исправлен native-only дефект: Codex мигрировал три статические source commands
в дополнительные skills. Явный `$ARGUMENTS` в canonical commands устраняет дубли; native
integration test подтверждает ровно 11 Task identities.

## Доставка и проверки

Локальная native доставка: Task/Core 0.17.0, изменённые domain units 0.4.1.
Harness source version 0.4.2, mAInd 0.3.2. Это локальные версии из текущего checkout,
не опубликованный git tag. [native-install.json](native-install.json) фиксирует install results;
[native-delivery-verification.json](native-delivery-verification.json) — 691 skill/runtime
Markdown/Python файлов без расхождений с cache. Три Claude-only PHP agent файла исключены
явно: native skills manifest их не объявляет; agent parity здесь не заявляется.

| Проверка | Результат |
|---|---|
| Task qualification | 1 087 tests, GREEN; один существующий skip отсутствующего Artifex plan. Последующие runtime/native изменения: 71 и 50 focused tests GREEN. |
| Skiller qualification | 696 tests, GREEN; после последнего cleanup edge case — 14 owning tests GREEN. |
| Harness qualification | 655 tests, GREEN; instruction projections: 14 целей, zero diagnostics. |
| mAInd qualification | 558 tests, GREEN. |
| Генераторы | registry --check, Task provider --check, provider instructions/check, root docs — GREEN. |
| Документация | Skiller и Task standalone builds, umbrella build — GREEN. |
| Среда трёх проектов | Codex settings doctor: zero errors/warnings. mAInd provider trust GREEN. |

Независимое ревью выявило и закрыло три edge cases: одинаковое имя при разном содержимом
native cache, перезапись чужого .bak, false→true повтор одного per-skill пути. Регрессии
проверяют сохранение изменённых/чужих файлов, references, уникальных скиллов и last-wins.
Удалённые tracked generated files больше не ломают release attestation; исторический
snapshot и fail-closed для внешних/битых symlinks сохранены.

Сохраняются диагностические ограничения: общие каталожные profiles могут превышать условный
fallback discovery budget; они не являются фактическими наборами этих трёх проектов.
CoreX maind health сообщает прежний memory mode и отсутствие portable .mcp.json.example;
оба provider trust GREEN, это отдельные настройки, не причина текущего skills truncation.

## Обнаруженная особенность клиента

В этом Codex project-level `[[skills.config]] enabled=false` не скрывал legacy symlink
из native prompt, хотя тот же override через CLI скрывал его. Проверено отдельно с cwd
и `-C`, directory и SKILL.md paths. Поэтому выбранные 16 отключений CoreX реально
применены через owning cleanup управляемых ссылок. Само наличие записи в config не
выдаётся за доказательство неактивности. После cleanup список уменьшился с 93 до 77,
сокращения с четырёх до нуля. Файлы сохранены в backup, установка сохраняет глобальную plugin selection.
В конце работы отдельно замечено изменение глобальных model/effort: Terra/medium → Sol/high;
источник не установлен, нынешняя настройка сохранена. Варианты startup были явно закреплены
параметром `-m`, поэтому их сравнение не зависит от этой перемены.

## Сохранность и следующий шаг

Все consumer изменения обратимы. Backup расположены в `.swissknifeman/backups/` проектов,
`~/.swissknifeman/backups/skills-audit-*` и перечислены в [implementation-evidence.json](implementation-evidence.json).
Временные preimages перенесены в постоянный каталог `~/.swissknifeman/backups/`.
Чужие исходные dirty changes сохранены. Git commit, push и tagged release не выполнялись.

Следующее действие — обычная рабочая задача в одной из следующих сессий Edufy/Flexcrm/CoreX.
Проверить конкретный итог и Next, отсутствие лишнего интервью/restart и сохранность isolation/
authority. При повторном сбое нужен один точный transcript и owning repair; новый общий аудит
или новый master plan не требуются. Парные model execution replays на старом/новом corpus
не выполнялись: улучшение success rate, latency или token usage не заявляется. Для сравнения
моделей такие прогоны остаются отдельным измерением, а не условием принятия проверенной
локальной оптимизации и исправленных детерминированных дефектов.
