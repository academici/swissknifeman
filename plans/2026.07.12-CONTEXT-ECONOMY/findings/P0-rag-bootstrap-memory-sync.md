# P0 — RAG-выжимка: машинный bootstrap и межкомпьютерная память

Дата верификации: 2026-07-12. Движок: perplexity-web (search). Потребители: P7 (bootstrap),
D11/D12 D-лога. Источники: localbusinesssearch.com ai-agent-infrastructure-terminal-toolkit ·
gist.github.com/arasovic (claude dotfiles bootstrap) · паттерны claude-config/gaal.

## Bootstrap машины (Claude Code + агентный тулинг)

- Канон 2026 — **dotfiles-паттерн**: версионируемый репо + один идемпотентный bootstrap-скрипт;
  повторный запуск безопасен (clone-or-pull → symlink/merge → verify).
- Версионировать: settings, hooks/, skills/commands, MCP-описания, CLAUDE.md-baseline.
  НЕ версионировать: секреты/identity и авто-накопленную память.
- JSON-конфиги — **merge, не overwrite** (локальные overrides в отдельном файле,
  сливаются при apply); прецедент precedence: system < user < workspace.
- Обязателен `--dry-run`; пост-шаг верификации (CLI стартует, MCP отвечают, doctor зелёный).
- Командный сценарий: baseline общий, per-user — свой манифест проектов + local-overrides.

## Межкомпьютерная память (локальный демон с бинарным стором)

- **Shared-папка (Syncthing/Dropbox/NFS) для живого стора — анти-паттерн**: file-level sync
  не транзакционен, конкурентная запись двух машин = порча SQLite/бинарных индексов;
  допустима только для append-only снапшотов/экспортов.
- Рекомендуемые варианты: (1) **демон на одном хосте** (NAS/always-on) + доступ по
  Tailscale/LAN через API — единственный писатель, чистая семантика; минус: офлайн-машина
  теряет память; (2) **export/import событий** (event-log, JSON-снапшоты в синк-папке,
  конфликты LWW/CRDT) — безопасно, но требует реализации.
- Вердикт для нас (по критерию Owner «сложно — не стоит»): в релиз НЕ входит; roadmap-стаб
  с двумя вариантами выше. agentmemory-стор (`state_store.db`, бинарный) шарить папкой ЗАПРЕЩЕНО.
