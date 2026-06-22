## Summary

<!-- Что меняется и зачем. Это монорепо-зонтик `swissknifeman`: несколько
     независимых пакетов под общей крышей. -->

## Затронутые пакеты

<!-- Отметьте всё, что трогает PR -->

- [ ] `skiller` — реестр скиллов (skills/, реестр, connect/vendor)
- [ ] `harness` — настройка окружения Claude Code (permissions/MCP/хуки)
- [ ] `maind` — память + граф + координация
- [ ] `core` — общий stdlib-фундамент (затрагивает все пакеты сразу)
- [ ] docs / инфраструктура (docs/, install.sh, CI, marketplace)

## Тип изменения

<!-- feat | fix | refactor | docs | chore — Conventional Commits, на русском -->

## Checklist

- [ ] `scripts/validate.sh` зелёный в каждом затронутом пакете
      (`bash packages/<pkg>/scripts/validate.sh`)
- [ ] Изменения в `core/` — оба зависимых пакета (skiller + maind) проходят validate
- [ ] Скиллы: `SKILL.md` имеет frontmatter (name·bucket·version·description);
      snippets — `index.json`; нет имён конкретных проектов/секретов
- [ ] Плагины/бакеты/команды менялись → прогнан `skiller registry`
      (регенерит `.claude-plugin/marketplace.json`, skills.json, индекс, граф)
- [ ] Новый пакет/команда → есть `.claude-plugin/plugin.json` с непустым description
- [ ] Содержательное изменение → обновлены `docs/` и затронутые `CLAUDE.md`

## Test plan

- [ ] CI / validate проходит для затронутых пакетов
- [ ] Установка: `./install.sh --bin-dir <tmp>` ставит `skiller` · `harness` · `maind`
- [ ] (если уместно) проверка вручную: команды CLI / slash-команды плагина
