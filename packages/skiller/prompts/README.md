# prompts — промт-библиотека swissknifeman

Готовые промты для рутины над реестром скиллов: аудит, ревью, генерация. Это
**не скиллы** (их не видит агент в проектах) — это шаблоны, которые ты руками
вставляешь в Claude Code или Perplexity, когда занимаешься сопровождением самого
реестра.

```
prompts/
├── audit/      # проверки качества и актуальности
│   ├── claude-skill-audit.md       # аудит одного SKILL.md (Claude)
│   ├── claude-repo-audit.md        # аудит всего реестра (Claude)
│   ├── perplexity-repo-audit.md    # внешний аудит репозитория (Perplexity)
│   └── perplexity-tech-radar.md    # актуальность технологий/версий (Perplexity)
├── review/     # код-ревью и сравнение
│   ├── claude-pr-review.md         # ревью PR к реестру
│   └── claude-skill-compare.md     # сравнение двух похожих скиллов (дубль?)
└── generate/   # создание и трансформация
    ├── claude-new-skill.md         # новый скилл по схеме
    ├── claude-compact-skill.md     # компактизация SKILL.md
    └── claude-translate-skill.md   # разовый перевод внешнего материала для анализа
```

## Модели

Где промт упоминает идентификатор модели — используй актуальные:
`claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5`. Не копируй устаревшие
id из внешних аудитов.

## Связь с тулингом

Структурные проверки (frontmatter, `name==dir`, semver, резолв `requires`, циклы)
уже автоматизированы в [`scripts/validate.sh`](../scripts/validate.sh) — промты
аудита для того, что машина не ловит: пересечения по смыслу, водность, устаревшие
факты, дубли. Бюджет токенов — `skiller budget` и
[карта бюджета](../docs/guide/budget.md).
