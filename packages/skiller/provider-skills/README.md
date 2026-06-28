# provider-skills — навыки для внешних агентов (paste-in)

SSOT портируемых **навыков-капабилити для внешних агентов** (Perplexity, и т.п.), которые
доставляются **ручной вставкой** в UI провайдера, а не через connect/vendor реестра скиллов.

> Отличие от `skills/`: те грузит сам Claude Code (прогрессивное раскрытие). `provider-skills/` —
> текст, который **человек копирует** в провайдера (Perplexity → My Skills / Custom Instructions).
> Канон живёт здесь (versioned, один источник); потребители (напр. Brain
> `40-AI/Workflow/PERPLEXITY/idea-architect.md`) держат **provenance-linked копию** (в шапке —
> ссылка на этот SSOT, ручной ресинк), не независимый форк.

## Раскладка

```
provider-skills/
└── perplexity/
    └── idea-architect.md   # Idea Architect & Startup Auditor (режимы Idea/Spec/Architecture)
```

## Как деплоить

1. Открыть нужный файл (напр. `perplexity/idea-architect.md`).
2. Скопировать тело (без служебного заголовка про деплой) в провайдера:
   - **Perplexity:** My Skills → Custom Instructions (или загрузка файла, если поддерживается).
3. Навык активируется по типу запроса (см. «Режимы активации» внутри).

## Провенанс

Внешняя методология (Anthropic Founder's Playbook, CB Insights, Anthropic context-engineering) —
выверена через RAG; карточка в `docs/reference.md`. Правки — здесь (SSOT), затем синк в потребителей.
