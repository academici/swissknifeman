## 5. Каталог прав и ролей

Права действуют в scope и наследуются вниз (`instance → workspace → project → plan → run`; `host` — отдельная ветка
instance). Токен сужает (`TokenGrant`). Отказ — `FORBIDDEN` с `details.permission`, `details.scope`,
`details.reason_code` (§6.3).

| Право | Модуль | Что разрешает | owner | maintainer | member | viewer | worker |
|---|---|---|:-:|:-:|:-:|:-:|:-:|
| `principal.manage` | access | создавать/отключать principals | ✓ | | | | |
| `membership.manage` | access | выдавать/отзывать членство | ✓ | ✓ | | | |
| `token.own` | access | свои токены | ✓ | ✓ | ✓ | ✓ | ✓³ |
| `token.any` | access | токены других (включая worker) | ✓ | ✓ | | | |
| `config.read` | settings | читать/explain конфиг, `settings.get_generation`, `platform.doctor` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `config.write` | settings | писать записи уровней `project`, `plan`, `run` | ✓ | ✓ | ✓ | | |
| `config.write_shared` | settings | писать записи уровней `instance`, `workspace`, `host` | ✓ | ✓ | | | |
| `config.lock` | settings | lock/unlock (instance/workspace) | ✓ | | | | |
| `workspace.create` | workspace | создавать workspaces (scope instance) | ✓ | | | | |
| `workspace.read` | workspace | видеть workspace | ✓ | ✓ | ✓ | ✓ | ✓ |
| `workspace.manage` | workspace | архивировать, настройки | ✓ | ✓ | | | |
| `project.create` | workspace | создавать проекты | ✓ | ✓ | | | |
| `project.read` | workspace | читать проект | ✓ | ✓ | ✓ | ✓ | ✓ |
| `project.manage` | workspace | архивировать, репозитории проекта | ✓ | ✓ | | | |
| `repo.manage` | workspace | регистрировать репозитории/remotes | ✓ | ✓ | | | |
| `host.manage` | workspace | регистрировать хосты (instance) | ✓ | | | | |
| `checkout.bind` | workspace | привязывать/перепроверять checkout | ✓ | ✓ | ✓ | | |
| `checkout.read_locator` | workspace | видеть локальные пути | ✓ | ✓ | ✓ | | ✓ |
| `worker.register` | workspace | регистрировать worker, менять его состояние | ✓ | ✓ | | | |
| `file.read` | artifacts | читать файлы/содержимое | ✓ | ✓ | ✓ | ✓ | ✓² |
| `file.write` | artifacts | добавлять файлы/версии | ✓ | ✓ | ✓ | | ✓² |
| `ext.read` | extensions | видеть пакеты/ресурсы | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ext.install` | extensions | устанавливать/карантин | ✓ | ✓ | | | |
| `policy.read` | policy | видеть полномочия/intents/профили | ✓ | ✓ | ✓ | ✓ | ✓ |
| `intent.approve` | policy | approve/deny intents | ✓ | ✓ | | | |
| `runtime.read` | runtimes | каталог, capabilities, роутинг | ✓ | ✓ | ✓ | ✓ | ✓ |
| `runtime.manage` | runtimes | record host runtimes / verification | ✓ | ✓ | | | ✓⁴ |
| `plan.read` | planning | читать планы/ревизии | ✓ | ✓ | ✓ | ✓ | ✓ |
| `plan.create` | planning | создавать планы, импорт | ✓ | ✓ | ✓ | | |
| `plan.edit` | planning | drafts (open/save/rebase/abandon) | ✓ | ✓ | ✓ | | |
| `plan.publish` | planning | публиковать/восстанавливать ревизии | ✓ | ✓ | ✓ | | |
| `plan.approve` | planning | подписывать визы ревизий | ✓ | ✓ | | | |
| `plan.archive` | planning | архивировать | ✓ | ✓ | | | |
| `context.assemble` | context | standalone assembly and finalization | ✓ | ✓ | ✓ | | |
| `context.read` | context | explain/diff контекста, research-кэш | ✓ | ✓ | ✓ | ✓ | ✓ |
| `context.research` | context | `context.record_research_result` | ✓ | ✓ | ✓ | | ✓² |
| `run.read` | execution | читать запуски | ✓ | ✓ | ✓ | ✓ | ✓² |
| `run.start` | execution | readiness, старт, review по запросу, autopilot start | ✓ | ✓ | ✓ | | |
| `run.control` | execution | pause/resume/cancel/restart/skip/reconfigure, autopilot pause/drain/stop | ✓ | ✓ | ✓ | | |
| `inbox.read` | execution | видеть decision requests | ✓ | ✓ | ✓ | ✓ | |
| `inbox.answer` | execution | отвечать на вопросы | ✓ | ✓ | ✓ | | |
| `check.verdict` | execution | verdict manual check | ✓ | ✓ | ✓ | | |
| `deviation.accept` | execution | принимать отклонения | ✓ | ✓ | | | |
| `worker.claim` | execution | worker-протокол, heartbeat, `context.finalize_manifest`; assignment-токеном не авторизуется | | | | | ✓ |
| `step.note` | execution | заметка/вопрос шага runtime-ом (только `execution.record_step_note` без claim под assignment-токеном) | | | | | ✓² |
| `integration.read` | integrations | desired/applied/hook policy/drift/doctor | ✓ | ✓ | ✓ | ✓ | |
| `integration.apply` | integrations | record projection applied/remove | ✓ | ✓ | ✓ | | |
| `hook.manage` | integrations | запись `hooks.subscriptions`, test/retry доставок, trust host-подписок | ✓ | ✓ | | | |
| `memory.read` | knowledge | поиск памяти, граф | ✓ | ✓ | ✓ | ✓ | ✓ |
| `memory.write` | knowledge | remember/forget, import graph | ✓ | ✓ | ✓ | | ✓ |
| `lesson.read` | knowledge/learning | lessons, кандидаты, `learning.record_activity` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `lesson.curate` | knowledge/learning | promote/deprecate, review candidates, recompute | ✓ | ✓ | | | |
| `export.run` | exports | экспорт, vault | ✓ | ✓ | ✓ | | ✓⁵ |
| `admin.storage` | platform | storage verify/repair, backup, migrations через API, prune orphans | ✓ | | | | |
| `admin.events` | platform | dead outbox: список, повтор | ✓ | | | | |
| `system.bootstrap` | access | `access.bootstrap_local_owner` | | | | | |
| `system.internal` | platform | *internal*-команды (§4) | | | | | |

² Ограничение run/assignment относится к токену `kind=assignment`, передаваемому runtime: записи — только
в scope своего run и в пределах grant.permissions; чтение предков run разрешено по access §4.4, step.note
дополнительно проверяет assignment/step/fence. Управляющий `kind=worker` токен host worker-а имеет workspace-права
роли по membership, не ограничен одним assignment и runtime-у не передаётся; file-read worker-а требует активного
AccessGrant. `file.write` worker-principal — только `SkmClient.upload_blob` (staging) в workspace своей регистрации: file versions evidence/patch/snapshot создаёт сервер
в execution-командах (K8). ³ self-право: свои токены без membership (`access.md`
§4.4 строка 5c); worker — только `access.rotate_token` / `access.revoke_token` своего текущего токена (`create_token`
для principal-а вида `worker` запрещён доменом). ⁴ worker — только на `host:H` своего хоста (`access.md` §4.4 строка 6a).
⁵ worker — только `exports.list_pending_notes`/`exports.record_note_written` в workspace worker-а (служба `vault_push`);
прочие команды `export.run` — `allowed_kinds = {human, service}`. `system.*` не входят ни в одну роль и не выдаются токенами
(`NON_GRANTABLE_BY_TOKEN`); их имеет только `SYSTEM_ACTOR` (§4.0.2). Ключ конфига с `x-skm.write_permission` требует
это право дополнительно к `config.write`/`config.write_shared` (первое применение: `hooks.subscriptions`,
`hooks.host.trusted` → `hook.manage`); набор прав команды по DTO задаёт `CommandSpec.permissions_of`.

---
