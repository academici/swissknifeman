---
layout: home

hero:
  name: analyst
  text: Непрерывное обучение экосистемы
  tagline: Детерминированный захват «выстраданных уроков» из прогонов Claude Code — с человеком в гейте, без авто-записи
  actions:
    - theme: brand
      text: Что такое analyst
      link: ./guide/
    - theme: alt
      text: CLI и команды
      link: ./guide/cli
    - theme: alt
      text: Архитектура
      link: ./architecture

features:
  - title: 🎯 Детерминированный захват
    details: digest извлекает кандидат-уроки из run-report по высокоточным сигналам (resolved-failure, workaround). Не «угадывает инсайты» — stdlib, on-demand, без демона.
  - title: 🧑‍⚖️ Человек в гейте
    details: Переход урока в curated и промоут в скилл — только с явного согласия человека. Авто-запись в скиллы ЗАПРЕЩЕНА — инвариант пакета.
  - title: 🔒 Приватность по дизайну
    details: Сырьё (raw-транскрипт) — LOCAL-only. Наружу (в память mAInd, в cross-project индекс) идёт только абстрагированный trigger→action. Секреты — по ссылке.
  - title: 🌐 Cross-project паттерны
    details: scan обходит реестр проектов, кластеризует уроки по Jaccard и детектит паттерны в ≥N проектах — namespace-изолированно (паттерн из ns:axioma не течёт в чужой).
  - title: 📈 Confidence-жизненный цикл
    details: recompute пересчитывает уверенность (Beta-среднее × volume × decay) из append-only events.ndjson → числовая state-machine и тиры. Детерминизм — восстановим из логов.
  - title: 🧩 Мост в скиллы (P4)
    details: suggest превращает cross-project паттерн в ЧЕРНОВИК SKILL.ru.md в staging — человек дорабатывает и промоутит. Не пишет в skills/, не генерит EN, не регистрирует.
---
