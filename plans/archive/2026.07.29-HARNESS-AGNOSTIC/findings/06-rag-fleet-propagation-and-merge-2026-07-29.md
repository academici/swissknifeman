# Слой 1 — распространение изменений на флот и механика возврата (2026-07-29)

Сырьё фазы **P5**. Вопрос захода: что физически получают онбордженные проекты в момент,
когда ветка изоляции сливается в `main`, и на каких фактах стоит приёмка инварианта брифа
М10 («текущие проекты не отваливаются»). Каждый факт — с источником, датой и вердиктом.

---

## Ф23 — Плагины локального marketplace НЕ обновляются автоматически (first-party)

**Источник:** прямой WebFetch `https://code.claude.com/docs/en/discover-plugins`, 2026-07-29.

Дословные утверждения доки:

- «Official Anthropic marketplaces have auto-update enabled by default. **Third-party and
  local development marketplaces have auto-update disabled by default.**»
- Обновление листинга — явная команда: «Refresh plugin listings from a marketplace:
  `/plugin marketplace update marketplace-name`».
- Применение в текущей сессии — вторая явная команда: «When you install, enable, or disable
  plugins during a session, run `/reload-plugins` to pick up all changes without restarting».
- Рантайм-носитель — КЭШ, а не рабочее дерево: «**plugins are copied to a cache**, so paths
  referencing files outside the plugin directory won't work»; починка залипшего состояния —
  «clear the cache with `rm -rf ~/.claude/plugins/cache`».
- Когда auto-update ВКЛЮЧЁН: «Claude Code checks for marketplace and plugin updates after
  your session starts, with a random delay of up to ten minutes, so the running session keeps
  using the versions it loaded at launch».

**Вердикт:** merge в `main` сам по себе НЕ доставляет новые/исправленные скиллы онбордженным
проектам connect-канала. Наш marketplace — локальный (`.claude-plugin/marketplace.json` в
дереве монорепо, потребители подключены путём), то есть попадает ровно в класс «local
development marketplace» с auto-update **выключенным** по умолчанию. Доставка требует
действия НА СТОРОНЕ ПРОЕКТА (`/plugin marketplace update` + `/reload-plugins`).

**Что это меняет для плана:** приёмка P5 меряет **доступность и здоровье контура**, а не
«флот получил новые правила». Раскатка правил (скиллы, agent-packs, `harness instructions`)
остаётся отдельной работой с собственным гейтом — она уже числится в `deferred` handoff'а.

---

## Ф24 — Тот же вопрос через RAG-синтез (вторичный источник, подтверждает Ф23)

**Источник:** `perplexity-web` search, 2026-07-29; цитируемые источники —
`code.claude.com/docs/en/discover-plugins`, GitHub issues `anthropics/claude-code#17361`
(январь 2026) и `#28540` (февраль 2026).

Сводка: «plugins do NOT update automatically just because files changed on disk»; после
первичной установки «the live filesystem is no longer consulted — the cache is the source of
truth until you explicitly update»; SHA-версионирование применяется, когда источник
marketplace — **git-URL**, а у сырого локального каталога версионным сигналом остаётся поле
`version` записи. Отдельно упомянуты два issue о том, что даже при `autoUpdate: true` кэш не
обновлялся.

**Вердикт:** совпадает с first-party в несущей части (нет автодоставки, кэш — носитель).
Часть про SHA-версионирование помечена **[UNVERIFIED]**: в first-party доке страницы
`discover-plugins` этого утверждения нет, а для нашего плана оно не несущее (мы не полагаемся
на автодоставку ни в каком виде). Issue-номера не проверялись — на решения не влияют.

---

## Ф25 — Замер живого дерева и инструмента (прямой прогон, 2026-07-29)

**Источник:** прогон на машине владельца в момент авторинга фазы.

```
$ git worktree list --porcelain
worktree <основное дерево>        HEAD 8e16a811…  branch refs/heads/main
worktree <дерево изоляции>        HEAD 8e16a811…  branch refs/heads/next/harness-agnostic
… + 11 сторонних detached-worktree в scratchpad чужой агентской сессии
$ git --version
git version 2.43.0
```

**Вердикт (что отсюда следует для фазы):**

1. `main` выкачан **в основном дереве** — значит merge исполняется ИМЕННО ТАМ, а не в дереве
   изоляции; это же дерево — цель симлинков CLI флота (замер P0.1), поэтому момент merge и
   есть момент переключения инструмента у потребителей.
2. Обе ветки сегодня стоят на одном коммите `8e16a811` — на момент авторинга ветка изоляции
   не несёт ни одного своего коммита, вся дельта плана ещё впереди.
3. В списке worktree присутствуют **11 сторонних записей** чужой агентской сессии
   (`/tmp/…/scratchpad/wt/*`). Они не наши: массовая уборка (`git worktree prune`, удаление
   чужих деревьев) в фазу НЕ входит — снимается ровно наше дерево по имени.
4. Версия git — 2.43.0; ни одна команда процедуры не должна опираться на флаги новее.
