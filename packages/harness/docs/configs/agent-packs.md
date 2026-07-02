# Agent-packs: паки субагентов и правил

Пак (`configs/claude-code/agent-packs/<pack>/`) — версионируемый бандл артефактов
Claude Code (агенты/воркфлоу/хуки/фрагмент settings/rules), который `harness`
детерминированно раскатывает в проект под стек или роль. Каталог паков, состав
файлов и полный список CLI-команд — в
[README пакетов](https://github.com/academici/swissknifeman/tree/main/packages/harness/configs/claude-code/agent-packs);
здесь — то, что нужно знать при работе с уже раскатанным паком: как читать
сгенерированный файл, где расширять поведение и как ловить дрейф.

```bash
harness agent-packs list
harness agent-packs render  --auto --pack <pack> --target .
harness agent-packs upgrade        --pack <pack> --target .
harness agent-packs remove         --pack <pack> --target . [--dry-run]
harness agent-packs doctor  --target . [--pack <pack>]
```

## laravel-package — паки для Laravel-пакетов

`laravel-package` (`packages/harness/configs/claude-code/agent-packs/laravel-package/`) —
стек-пак для тех, кто разрабатывает **Laravel-composer-пакет** (библиотека: `composer.json` без
`artisan`), а не приложение — включая монорепо PHP-пакетов (`packages/*/src`, как у chatom).
Отличие от `backend-laravel` (приложение: `route → controller → Action → DTO → policy`) — слайс-юнит
здесь «фича пакета» (контракт/интерфейс → реализация → регистрация в `ServiceProvider` →
publishables), а reviewer заточен на **публичный контракт** вместо access-layer: Public API/BC
(SemVer-дифф, `BC_CHECK_CMD` через `roave/backward-compatibility-check` при наличии бинаря — иначе
ось остаётся прозой), `register`-vs-`boot` в `ServiceProvider`, publishables (миграции/конфиг/views)
и тесты на Orchestra Testbench вместо `php artisan test`.

Дубль с `backend-laravel` не плодится: общие `review-gate.sh`/`review-gate.env.ini`/
`settings.fragment.json` резолвятся из `backend-laravel` через `src_pack` (см. ниже) вместо копий, а
общая проза (severity-формат, «Детект ≠ гейтинг») размечена `<!-- shared:name -->` в обоих паках и
сверяется байт-в-байт тестом (`test_agentpacks_shared.py`) — расхождение общего текста красное.
Профиль `php-package` (`packages/skiller/profiles/php-package.json`) называет
`agent_pack: ["laravel-package", "_common"]`, так что `maind onboard`/`sync` раскатывают пак
штатным путём вместе со скиллами.

Установка отслеживается в `.claude/agent-pack.lock.json` — по каждому файлу пака
там лежат `target`, `base_sha256` отрендеренного содержимого (**включая**
provenance-header, см. ниже) и `user_owned`.

## Provenance-header

Каждый сгенерированный файл пака (кроме `kind: merge` — тот вливается
фрагментом в чужой `settings.json`, свой заголовок там неуместен) получает
детерминированный блок-паспорт:

```md
<!-- swissknifeman:generated
Generated-by: harness agent-packs
Pack: backend-laravel@0.11.1
Template: agents/reviewer.md
Edit-policy: generated-core — НЕ редактируй; расширяй через extension-point
Extension-points: .claude/rules/acme-reviewer-overrides.md
Upgrade: harness agent-packs upgrade --pack backend-laravel --target .
-->
```

Поля:

- **Pack@version** — какой пак и какая версия сгенерировали файл;
- **Template** — исходник внутри пака (`src` из `pack.json`), если нужно найти
  первоисточник;
- **Edit-policy** — `generated-core` (файл перезаписывается паком при upgrade,
  редактировать бессмысленно) либо `user-owned` (файл отдан вам навсегда, пак
  его больше не трогает — см. ниже);
- **Extension-points** — куда писать проектные правки вместо генерённого файла
  (список `target`-путей файлов с `role: override` из манифеста пака; обычно
  один — `.claude/rules/<prefix>-reviewer-overrides.md`);
- **Upgrade** — готовая команда для накатки новой версии пака.

Заголовок **намеренно без timestamp**: он входит в `base_sha256` вместе с
остальным содержимым файла, и любая недетерминированность (дата генерации)
сломала бы idempotent re-render и сравнение lock↔диск при дрейф-детекте.
Синтаксис комментария подобран под расширение цели — `.md` получает HTML-блок
**после** закрывающего `---` YAML-frontmatter (иначе Claude Code перестал бы
парсить метаданные агента), файлы с шебангом — после первой строки, `.js`/`.mjs`
получают `//`-комментарий, `.sh`/`.ini` — `#`. Расширения вне этого набора
заголовок не получают вовсе — лучше без паспорта, чем сломанный синтаксис.

## «Generated core не редактируем»

Правило раскатывается всем стек-пакам общим `_common`-паком в
`.claude/rules/generated-assets.md` (область действия — `.claude/agents/**`,
`.claude/workflows/**`, `.claude/hooks/**`): файл с блоком
`swissknifeman:generated` — собственность пака, агент **не правит его напрямую
ни при одной находке ревью**, каким бы обоснованным ни казалось исправление.
Расширение — только через файл из `Extension-points` в заголовке или через
`.claude/rules/*-overrides.md`. Если правка ядра действительно необходима —
агент останавливается и отчитывается; сам upgrade пака или правку шаблона в
`harness` делает человек, а не агент (см. последний раздел).

Куда писать проектные оверрайды на практике: каждый стек-пак (`backend-laravel`,
`node-frontend`, `python-backend`, `dart-flutter`, `laravel-package`) ставит
`.claude/rules/<prefix>-reviewer-overrides.md` (`<prefix>` — ответ интервью
`PACK_PREFIX`, по умолчанию имя каталога проекта) с `user_owned: true` и
`role: override` в манифесте — это единственный файл пака, который upgrade
никогда не перезаписывает и не считает конфликтом. Заготовка пустая
(«Сюда — проектные оси ревью; пак этот файл не перезаписывает») — наполняется
по ходу работы над проектом.

## Drift-детект

```bash
harness agent-packs doctor --target . --drift              # информативно, rc=0
harness agent-packs doctor --target . --drift --strict      # CI-гейт, rc=1 при дрейфе
```

Сравнивает `base_sha256` из `.claude/agent-pack.lock.json` с реальным sha256
файла на диске — по каждому установленному паку и каждому его файлу, кроме
`kind: merge` (свой sha не отслеживается) и `user_owned` (дрейф там ожидаем и
не проблема — это же расширение). Результат — `modified` (кто-то правил
generated-файл руками мимо override) или `missing` (файл удалён/не читается).
Без `--strict` команда только печатает находки (годится для обычного
`doctor`-прогона); `--strict` превращает найденный дрейф в ненулевой код
возврата — используйте как CI-гейт «никто не правил generated руками мимо
override».

Тот же сигнал приходит и без явного вызова doctor: `maind analyze`
самостоятельно читает `.claude/agent-pack.lock.json` (не импортируя `harness` —
пакеты изолированы, формула sha256 продублирована буквально) и заводит
находки дрейфа в `pack_drift`. Вердикт прогона при дрейфе — **ATTENTION**
(никогда не RED — это подсказка на исправление, не провал прогона), причина в
отчёте так и звучит: «generated-файл пака правлен локально: `<target>` —
перенеси правку в override и восстанови (`harness agent-packs render`)».

## Как легально изменить core

Два способа, оба — работа человека, не агента:

1. **Upgrade пака.** Если правка нужна проекту прямо сейчас и уже есть в
   новой версии пака — `harness agent-packs upgrade --pack <pack> --target .`.
   Файлы категоризируются: `new`/`safe-apply` ставятся автоматически,
   `user-owned` не трогаются, `conflict` (правили и вы, и апстрим) пишется
   рядом как `<target>.pack-new` — смёржите руками и решите, что оставить.
2. **Правка шаблона в `harness`.** Если нужного поведения ещё нет ни в одной
   версии пака — меняется исходник пака в
   `packages/harness/configs/claude-code/agent-packs/<pack>/` (шаблон +
   `pack.json` версия + `CHANGELOG.md` пака), после чего изменение долетает до
   проектов тем же `upgrade`. Это правка исходного пакета `harness`, а не
   рендеренного файла в целевом проекте — обычный PR-процесс, `bash
   packages/harness/scripts/validate.sh` перед коммитом.

В обоих случаях источник истины остаётся один — `configs/claude-code/agent-packs/`
в `harness`; рендеренная копия в проекте вторична и восстановима командой из
`Upgrade:` в заголовке файла.

## Удаление пака

```bash
harness agent-packs remove --pack <pack> --target .              # удалить
harness agent-packs remove --pack <pack> --target . --dry-run    # только план
```

`remove` — безопасная обратная операция к `render`/`upgrade`, по каждому файлу
пака из lock:

- **чистый файл** (sha256 на диске совпадает с `base_sha256` из lock) — удаляется;
- **правленный локально** (sha256 отличается) — остаётся, с предупреждением;
- **`user_owned`** (расширение, отдано вам навсегда) — остаётся всегда;
- **`kind: merge`** (хуки, влитые в `.claude/settings.json`) — не трогается
  никогда (удаление фрагмента из чужого JSON небезопасно) — предупреждение со
  списком, что удалить руками при желании;
- **уже отсутствует на диске** — тихо пропускается.

Запись пака снимается из `.claude/agent-pack.lock.json` в любом случае (иначе
повторный `remove`/`render` видел бы уже удалённый пак как установленный);
если пак был последним в lock — файл lock удаляется целиком. `--dry-run`
печатает план (что будет удалено/оставлено) без единого изменения на диске.

## src_pack — шаринг файла между паками

`files[]`-запись в `pack.json` может нести необязательное поле `src_pack:
<имя-другого-пака>` — тогда исходник (`src`) читается из каталога УКАЗАННОГО
пака, а не из своего. Владелец файла (что уходит в `Pack:` заголовка,
команда `Upgrade:`) при этом остаётся текущий пак — `src_pack` влияет только
на резолв исходника, доставка/провенанс не меняются. Годится, когда несколько
паков должны раздавать один и тот же файл (напр. общий rules-фрагмент) без
физического дублирования содержимого в каждом паке.
