# plans/ — исполняемые мастер-планы монорепо

Каталог мастер-планов по протоколу `plan-protocol`: «сильная» модель (opus) проектирует план,
«дешёвая» (sonnet/haiku) исполняет его items без доступа к чату планирования. Каждый план —
каталог `plans/<PLAN-ID>/` с тремя видами файлов: `plan.md` (Meta, правила, Status Board, логи),
`phases/Pn.md` (по файлу на фазу: контекст + items + phase handoff), `handoff.md`
(rolling-указатель «где мы», перезаписывается).

- **Протокол (SSOT):** скилл `packages/skiller/skills/general/plan-protocol/` — схемы,
  6 канонических статусов, routing-матрица, эскалация; шаблоны — его `snippets/`.
- **Команды:** `/task:plan-design` · `/task:plan-exec` · `/task:plan-close` · `/task:plan-audit`.
- **Валидатор:** `python3 packages/task/scripts/plan-lint.py plans/<PLAN-ID>` (или `plans/` —
  все планы разом); exit 0 = формат чист. Из plugin-контекста команды зовут его через
  `${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py`; нет переменной — используй прямой путь выше.

**ПРАВИЛО MD-only:** источник истины плана — только Markdown с жёсткими маркерами.
Любой JSON — производный артефакт (`plan-lint --json`), руками не правится и не хранится.
