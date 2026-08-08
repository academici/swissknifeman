---
id: D121
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Provider-token budget P0.1 жёстко ограничен: восемь samples из восьми разных реальных файлов, каждый payload ≤16 KiB, суммарно ≤128 KiB; минимум три dense samples из трёх файлов и минимум два небольших файла целиком.** Sample несёт full-source hash, byte range и sample hash; все пять классов имеют ненулевое покрытие. Bound/tightness считаются честно только на samples; полные файлы проходят offline classifier/estimate canary без provider calls. **Consequences:** `supersedes D120` только в термине «8 файлов» → «8 provenance-qualified real samples»; ≤12 calls и строгие gates сохраняются. Полный provider corpus не является входным гейтом и расширяется только по field finding; артефакт не заявляет статистическую полноту.

## Почему

Прямое уточнение владельца: минимизировать токены разработки и переносить максимальные замеры на реальные проекты. Лимит уменьшает provider payload прежнего v1 corpus 394880 байт и схемы `3 × N` до максимум 131072 байт при сохранённом реальном происхождении данных. RAG:— (repo-grounded old corpus size + owner decision + deterministic arithmetic).
