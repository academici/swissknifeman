# Obsidian vault

Сценарий: AI-агент для работы с базой знаний — заметки, ТЗ, документация,
анализ идей.

## Установка

```bash
~/projects/packages/swissknifeman/install.sh --target ~/vaults/brain
```

Автодетект видит `.obsidian/` → профиль `obsidian-vault` → bucket-ы
**architect, pm, founder, operator, roles, imported**:

- `pm` — BRD, PRD, roadmap, монетизация: полный цикл проработки ТЗ;
- `founder` — идеи, анализ конкурентов, питчи;
- `architect` — когда заметка перерастает в архитектуру;
- `imported` — research- и knowledge-super-skills;
- `roles` — персоны для смены оптики (startup-cto, tech-lead).

## Permissions

Для vault-а достаточно `base` — кодовых стеков тут нет:

```bash
~/projects/packages/swissknifeman/scripts/apply-permissions.sh --target ~/vaults/brain
```

Автодетект не найдёт маркеров стека и применит только `base`: git, файловые
операции, curl — без промптов; секреты — под запретом.

## Связка с реестром

Vault может получать зеркало реестра скиллов — workflow `sync-to-brain.yml`
ежедневно синхронизирует `skills.json` в `brain/.ai/skills-registry/`, а
локально это делает:

```bash
BRAIN_PATH=~/vaults/brain ./sync.sh
```

Так база знаний всегда видит актуальный каталог скиллов — полезно, когда
заметки ссылаются на скиллы или агент в vault-е подбирает скилл под задачу.

## Типовой workflow

1. Идея фиксируется заметкой → скилл `founder/idea-analysis` раскладывает её
   по структуре;
2. идея зреет → `pm/brd`, затем `pm/prd-from-brd` превращают её в ТЗ;
3. ТЗ готово → `architect/*` проектирует решение;
4. проект стартует → [Laravel-сценарий](/examples/laravel) разворачивает
   рабочее окружение.
