# Структура PRD

Справочник к скиллу `prd-from-brd`.


```
1. TL;DR (3–5 строк) — что и для кого выпускаем
2. Цели и не-цели (in-scope / out-of-scope)
3. User personas (детали поверх BRD)
4. User flows (mermaid + текстовое описание)
5. Detailed user stories
   - Для каждой:
     - User story (как роль, я хочу..., чтобы...)
     - Acceptance criteria (Given / When / Then)
     - Edge cases / error states
     - Success metric
     - Приоритет (RICE score + версия)
     - Зависимости (другие stories или внешние)
6. UX requirements
   - Состояния экрана: empty / loading / success / error / partial
   - Accessibility minimum (WCAG 2.1 AA если применимо)
   - Mobile breakpoints (если веб)
7. Метрики запуска (north star + per-feature)
8. Открытые UX-вопросы (для дизайнера)
9. Out of scope для v1 (явный список)
```

---
