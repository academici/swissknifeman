# git-guardrails — хук блокировки опасных git-команд

PreToolUse-хук Claude Code, который перехватывает и блокирует деструктивные git-команды **до**
исполнения (на уровне `Bash`-инструмента). Особенно важно для production и embedded-проектов, где
случайный `git reset --hard`/`git push` на ветке устройства может потребовать физического доступа
к железу для восстановления.

## Что блокируется

`git push` (включая `--force`/`--force-with-lease`), `git reset --hard`, `git clean -f`/`-fd`,
`git branch -D`, `git checkout .`/`git restore .`, `git rebase --onto`.

## Провенанс

Производное от [mattpocock/skills](https://github.com/mattpocock/skills) →
`misc/git-guardrails-claude-code/scripts/block-dangerous-git.sh` (MIT, © Matt Pocock). Расширено
паттернами `force-with-lease` и `rebase --onto`, сообщение переведено на русский. В нашей архитектуре
хуки принадлежат пакету **harness** (skiller делегирует окружение сюда) — поэтому скрипт живёт здесь,
а не как скилл.

## Как включить

Файл хука ставится глобально вместе с остальными (`harness hooks --global` → `~/.claude/hooks/`).
Затем зарегистрировать PreToolUse-хук в settings проекта (`.claude/settings.json`) или глобально
(`~/.claude/settings.json`), merge-only:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "~/.claude/hooks/git-guardrails/block-dangerous-git.sh" }
      ] }
    ]
  }
}
```

Скилл-обёртка с пошаговой инструкцией — `general/git-safety` (реестр skiller).

## Проверка

```bash
echo '{"tool_input":{"command":"git push origin main"}}' | ./block-dangerous-git.sh
# → exit 2 + сообщение BLOCKED в stderr
```

## TODO (follow-up)

Завести флаг `harness hooks --git-guardrails on|off` (по образцу `--auto-approve`), который сам
регистрирует PreToolUse-хук в settings проекта — чтобы не править settings.json руками.
