# Отчёт об исправлениях skm для плана TARGET-ARCH (для сессии, которая ведёт план)

Дата: 2026-10-20. Репозиторий skm: ветка `main`, коммиты `b47f8c60c..HEAD`, **локальные, не запушены**
(`git -C <skm> show <sha>` показывает любой из них). Основание: `target-arch-docker-sandbox-problem.md` (разделы 3–10) и
журнал T1–T21. Подробности по каждому пункту с тестами и остатками — раздел 11 того же файла; здесь то, что нужно, чтобы
подкорректировать работу над планом.

## 1. Что поменять в своей работе (коротко)

1. **Запускайте пункты через `--options` шаблона (`i1.json`, `e1.json`) без `orchestration` в пункте плана.** Claim теперь
   называет исполнителя из `--options` (provider, model, effort). Уже записанные `orchestration` можно убрать через
   `skm planner set`; пока они остаются, они имеют приоритет над `--options` при claim (см. П.1 ниже), поэтому они должны
   совпадать с шаблоном или быть удалены.
2. **Перед каждым запуском делайте `run --dry-run`** с теми же `--options`: он печатает `claim_actor` и в `warnings`
   предупреждает, если actor не совпадает с маршрутом исполнителя.
3. **Ждите от исполнителя `done_pending_checks`, а не `blocked`**, если он не смог запустить проверки (docker, `.git`, сеть).
   Тогда checks-stage сам выполняет V1–V6, пункт регистрируется `done` с evidence. `blocked` исполнителя теперь означает
   только «нужен владелец» (решение, путь вне write set, учётные данные).
4. **`planner next` теперь делит батч по шаблону маршрута** (`later` в JSON и в строке батча). Запускайте первую группу с её
   `--options`, остальные группы — следующими запусками. Ручное разбиение больше не нужно.
5. **Формулировку правил плана «финиш пункта» вместо «`plan.py finish`» можно вернуть** (обход T5 больше не нужен): brief
   отклоняет только указание запустить команду, описание гейта проходит.
6. **Docker на машине владельца теперь rootless** (см. раздел 4): первые прогоны с контейнерами пересоберут образы и будут
   медленными; следите за пунктами про сокет и порты.
7. **P2.1** (код в коммите edufy `d1e1d382`, V1–V3 были пройдены вручную): теперь его можно закрыть штатно. Reopen P2.1,
   запуск с `--options i1.json --adopt`: исполнитель принимает работу, возвращает `done_pending_checks`, checks-stage
   выполняет V1–V3 на rootless docker. Ручное закрытие через `planner finish` оркестратором по-прежнему упирается в
   классификатор безопасности, но больше не нужно.

## 2. Коммиты

| # | Пункт | Коммит | Раздел отчёта |
|---|---|---|---|
| P1 | claim называет исполнителя из `--options` | `368117e12` | 10.3, T1, T3 |
| P2 | dry-run показывает actor claim | `2ba5e894e` | 10.3, T2 |
| P3 | промпт исполнителя без acceptance-команд | `fe24f49a6` | 3.3, 6.1.A, 6.1.C |
| P4 | статус `done_pending_checks` | `003ebc3fe` | 6.1.B |
| P5 | brief: команда запуска ≠ описание гейта | `4a0b84262` | 10.2, T5 |
| P6 | `planner next` делит батч по шаблону | `5aeac75a8` | 6.3.G, 10.4, T15 |
| P8a | переопределение каталога запуска конфигурацией | `8923d56ad` | 6.3.F |
| — | раздел «Исправления» в отчёте | `bcf2a2e57` | 11 |
| P7a | проверка окружения Docker и первая инструкция | `4fbb5146f` | 6.2.E |
| P8b | дедупликация `launch-catalog.json` | `88f8e1781` | 6.3.F, пожелание владельца |
| P7b | зонд Docker отдельно от оркестрации; полная инструкция | `049817203` | 6.2.E |

Полные хеши: `git log --format='%H %s' b47f8c60c..HEAD`.

## 3. Что изменено по пунктам и что это значит для вас

### P1 — claim из `--options` (`368117e12`)
- Было: `claim_actor` брал только исполнителя по умолчанию без effort; пункт с `route.provider=codex` получал
  `ROUTE_MISMATCH`/`ROUTE_UNDERSHOOT` при зелёном dry-run.
- Стало: `packages/orch/lib/orch/conductor/application/loop.py` — actor claim = ступень `executor` файла `--options`
  (provider, model или модель класса, effort). Без опций — прежний исполнитель по умолчанию без effort (чтобы не появился
  новый `ROUTE_UNDERSHOOT` для маршрутов без модели).
- Приоритет: мост (`bridges/planner-orch/worksource.py`, `executor_actor`) всё ещё берёт исполнителя из `orchestration`
  плана раньше actor claim. Если и план, и `--options` называют исполнителя, claim проверит исполнителя плана, а запустится
  исполнитель `--options` (итоговые опции: `--options` побеждает). Совет: убрать `orchestration` из пунктов.
- Тесты: `ClaimActorTests` (orch), `test_a_piece_routed_to_another_executor_starts_under_the_claimed_actor_without_orchestration` (мост).

### P2 — dry-run (`2ba5e894e`)
- `run --dry-run` печатает `claim_actor` (то, что уйдёт в `source claim --actor`) и `warnings` при расхождении
  provider/model/effort с маршрутом исполнителя. Actor без effort не противоречит маршруту с effort.
- Тесты: `PreviewClaimActor`.

### P3 — промпт без команд (`fe24f49a6`)
- При `checks.executor_runs_checks: false` (по умолчанию) раздел Acceptance называет проверку по id и ожиданию
  (`command: withheld`), Verification перечисляет проверки без команд, запрещает docker и контейнеры, велит оформлять
  недоказуемое как `pending`. Голдены `executor-*` обновлены.
- Остаток: файл `input.json` в каталоге пункта хранит команды; промпт его не вставляет, но исполнитель может его прочитать.
- Тесты: `WithheldChecksTests`; один старый тест (искал команду в промпте) изменён под новое поведение.

### P4 — `done_pending_checks` (`003ebc3fe`)
- Стадия-отчёт допускает `done_pending_checks` (нужна запись `pending`). Checks-stage идёт как после `done`; красные
  проверки правятся обычным путём; при зелёных пункт регистрируется `done` с evidence и одной записью `note` вместо
  `pending`. Если ни одна проверка не запускалась (все пропущены `checks.cadence`/`kinds`) — блок `CHECKS_NOT_RUN`.
- Статус не регистрируемый: схемы planner и work source не менялись, `planner finish --check --evidence` получает
  доказательства checks-stage как раньше.
- Что увидите в прогоне: `stage.end` исполнителя с `verdict: done_pending_checks`, затем `checks.1`, `register done`.
- Тесты: `DonePendingChecksTests` (полный путь до регистрации и коммита, красные проверки, `CHECKS_NOT_RUN`).

### P5 — brief (`4a0b84262`)
- `bridges/planner-orch/brief.py`: отклоняет указание запустить `plan.py start|finish`, `unit return`, `planner:plan-run`
  (глагол запуска без отрицания, приглашение shell, кодовый блок); описание гейта проходит; `report_api` — при любом
  упоминании. Правила плана (`plan.rules`) остаются данными, как и были.
- Остаток: эвристика (глаголы запуска en/ru, отрицания, «перед/после»); нестандартная формулировка приказа может пройти.

### P6 — `planner next` (`5aeac75a8`)
- `packages/planner/lib/planner/plan/lifecycle.py`: готовые пункты `recommended`-батча группируются по шаблону `route`;
  первая группа — команда запуска; остальные — `later` (JSON, схема `read-ready`) и строка батча. Цепочки зависимостей
  остаются вместе под максимальным route, пункты без route едут с первой группой, `required` не делится, старт группы не даёт
  предупреждения о разбиении.

### P8a — переопределение каталога (`8923d56ad`)
- `[orch.launch] catalog` (файл вместо поставляемого, только machine/invocation/flags) и
  `[orch.launch.entries.<роль>_<провайдер>]` (например `executor_codex`): меняются только отличающиеся поля.
  `model_class`, `effort`, `timeout_s` можно и в проекте; `argv`, `transport`, `model_set` — только machine/invocation/flags.
  Источник значения виден в `route explain` и `orch launch show` (`changed_by`).
- Пример для проекта (`.swissknifeman/config.toml`): `[orch.launch.entries.executor_codex]` + `effort = "xhigh"`.

### P8b — дедупликация каталога (`88f8e1781`)
- `packages/orch/configs/launch-catalog.json`: 13,7 КБ → 7 КБ; хранит `defaults`, общие поля роли, именованные части argv
  (`parts`, `@имя`) и у провайдера только отличия. Песочница и ограничения инструментов остаются в argv самой записи.
- Разрешённый каталог не изменился: он закреплён снимком `packages/orch/tests/golden/launch-catalog-resolved.json`
  (снят с файла до рефакторинга); `catalog_version` прежний; файл в старом виде по-прежнему принимается.
- Файл в классе security: любое изменение команды, флага песочницы, класса, effort, транспорта или таймаута записи роняет
  `test_launch_compact`, пока снимок не обновлён как ревью.

### P7 — Docker (`4fbb5146f`, `049817203`)
- Доступ исполнителя к docker **не дан** и не нужен: после P3/P4 контейнерные проверки делает checks-stage.
- Проверено на этой машине (codex 0.160.1): песочница `:workspace` не пускает к unix-сокету; список `unix_sockets` в профиле
  прав работает только через прокси сети codex, docker CLI подключается напрямую; единственный рабочий вариант
  `network.enabled = true` открывает все сокеты пользователя, включая rootful. Поэтому профиль «docker для исполнителя» не
  лучше текущей схемы. Лучшая практика (Docker, Codex, Perplexity): rootless docker под отдельной учётной записью.
- Сделано: необязательный зонд окружения `orch.docker`, `orch.docker-credentials`, `orch.docker-compose`
  (`skm doctor --unit orch --category environment`, `packages/orch/scripts/docker-env-check.py`). Он **отдельно от
  оркестрации**: запуски, claim, conductor и `orch doctor` его не вызывают; каждая команда docker ограничена 5 с;
  `warn` указывает на `packages/orch/docs/docker-environment.md` один раз.
- Инструкция `docker-environment.md` описывает построение с нуля на чистой Ubuntu 24.04 (установка Docker Engine из apt,
  зависимости rootless, AppArmor, linger, контекст, проверка, выход из группы `docker`, делегирование cgroup, порты <1024,
  отличия rootless, очистка rootful, откат, таблица неполадок).

## 4. Docker на машине владельца (состояние на конец работы)

- Rootless-демон создан и запущен: пользовательская служба `docker`, `Linger=yes`, контекст `rootless` текущий, сокет
  `/run/user/1000/docker.sock`, `SecurityOptions` содержит `name=rootless`, `hello-world` отработал, зонд даёт три `ok`.
- Rootful-демон ещё работает рядом (`/var/run/docker.sock`, группа `docker`); владелец сказал, что его данные (24 образа,
  32 тома, 5 контейнеров) можно очищать. Выход из группы `docker` и остановка rootful — на усмотрение владельца
  (команды в `docker-environment.md`). До этого root-эквивалентный доступ остаётся возможным через `docker --context default`.
- Хранилище rootless **пустое**: все образы и тома edufy собираются заново (первый прогон долгий; места на диске 84 ГБ).
- Что может отличаться в edufy при rootless (проверьте на первом прогоне):
  1. compose-файл или инструмент монтирует `/var/run/docker.sock` внутрь контейнера: нужен `/run/user/1000/docker.sock`
     (`$XDG_RUNTIME_DIR/docker.sock`);
  2. публикация портов ниже 1024 (нужен `net.ipv4.ip_unprivileged_port_start` или высокий порт);
  3. владельцы файлов в bind mount: root внутри контейнера = пользователь снаружи; непривилегированный пользователь внутри
     контейнера выглядит как sub-uid (`100000+`) снаружи;
  4. ограничения ресурсов (`--cpus`, `--memory`) без делегирования cgroup (в инструкции есть шаг);
  5. скорость сети slirp4netns ниже родной (для тестов не критично);
  6. `docker-credential-desktop` из T13 больше не мешает (владелец убрал строку из `~/.docker/config.json`; зонд проверяет).
- Откат за секунду: `docker context use default`.

## 5. Проверка

- Последний прогон `python3 scripts/affected-tests.py --run` (после всех коммитов): тесты orch, мостов
  (`gui-orch`, `orch-harness`, `orch-skiller`, `planner-orch`), `ecosystem-units check`, `public-hygiene`, `golden.py check` —
  все `[ok]`. Тесты planner (938) и `validate.sh` planner зелёные после P6 (planner с тех пор не менялся).
- Тесты orch после P8b/P7b: 1379+ (новые: `test_launch_compact`, `test_launch_overrides`, `test_docker_env`,
  `DonePendingChecksTests`, `WithheldChecksTests`, `PreviewClaimActor`, `LaunchConfigurationTests`, `ClaimActorTests`).
- Боевой прогон на edufy **не выполнялся**: все проверки на фейковых исполнителях и временных данных.

## 6. Не сделано и риски

- Профиль `sandbox: docker` для исполнителя: не реализован сознательно (см. П.7). Вернуться к нему можно, если владелец
  создаст отдельную учётную запись с rootless docker и попросит запуск роли под ней.
- Приоритет `orchestration` плана над `--options` при claim (П.1) — убрать дубли из пунктов edufy.
- Checks-stage запускает код агента на хосте от пользователя владельца; на rootless контейнер уже не root хоста, и это
  остаточный риск стал заметно меньше, но не исчез (тесты видят файлы пользователя).
- Эвристика brief (П.5) не доказательство.
- Тестовые файлы эксперимента с сокетами: `~/.sk-sock-test/` и `/tmp/sk-sock/` — удалить вручную (хук запретил `rm`).
- Локальный журнал `reports/target-arch-orch-run-log.md` (исключён из git, запись T22) и `.swissknifeman/` в edufy не менялись.
