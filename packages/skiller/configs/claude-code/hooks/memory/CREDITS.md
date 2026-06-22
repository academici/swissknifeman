# Источники и заметки — memory

Самодостаточная папка-хук «единой памяти». Структура и эргономика повторяют
`hooks/auto-approve/` (переключатель + `env.ini` MODE + `config.json` + `modes/`
+ `lib/`), чтобы режимы были взаимозаменяемы и переопределялись конфигом.

## Режимы

- **file / federation** — собственные, на markdown-файлах. Схема факта совместима
  с нативной памятью Claude Code (`name` / `description` / `metadata.type`),
  поэтому `federation` читает и свои `memory/` участников, и нативные
  `~/.claude/projects/<slug>/memory/`.
- **agentmemory** — прокси к стороннему **AgentMemory**
  (`@agentmemory/agentmemory`, npm), который крутится демоном на Brain
  (`cd ~/Vaults/Brain && npm run memory:start`, HTTP по умолчанию `:4111`).
  Точная форма HTTP-API зависит от версии пакета — пути (`/memories`, `/search`,
  `/health`) и jq-выборка в `modes/agentmemory.sh` помечены как требующие сверки
  с реальным инстансом при первом прогоне. Недоступность демона → честное
  сообщение, без падения.

## Что НЕ делает

Хук ничего не удаляет и не перезаписывает чужие факты; `remember` только
дописывает. Установка через `apply-permissions.sh --global` обновляет код/lib/modes,
но НЕ перезатирает `env.ini`/`config.json` (там твой выбор режима и состав групп).
