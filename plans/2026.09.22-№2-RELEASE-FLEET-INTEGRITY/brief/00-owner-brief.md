# Owner brief

Владелец потребовал создать и полностью исполнить plan-protocol план: исправить
ложнозелёный `v0.24.0`, сделать Task `0.24.0` во всех принадлежащих поверхностях,
проверить прочие unit versions по ownership, подготовить следующий корректный
release candidate, мигрировать все registered enabled projects на marketplace/native
delivery для Claude Code, Codex и Cursor, удалить только доказанно managed legacy
копии/locks/caches и получить полный before/after отчёт. Разрешены локальные
исправления, генерация, fleet sync и проверки. Запрещены push, force-push,
публикация GitHub Release и перемещение tags без отдельного разрешения.

Дополнение владельца: процесс должен предотвращать повторение — после новой локальной
версии штатный workflow автоматически копирует/синхронизирует проекты, удаляет либо
инвалидирует старые caches, валидирует tags и закрепляется отдельным правилом/skill
для последующих package/umbrella releases.
