# HANDOFF — 2026-08-01 — after P5.9

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high

| Параметр | Значение |
|:--|:--|
| Model | implementation |
| Thinking | high — ремедиация §3.1 supply-chain (P5.10 Routing); необратимая правка вендоренного бандла + пиновка внешнего SHA, effort high+ по §9 |
| Context | continue (/clear) — ручной item |
| Суть | P5.10: вендоринг пинованного payload `web-design-guidelines` + перевод бандла в `strategy=fork`; P5.9 не блокирует (независимые файлы) — текущая сессия уже sonnet/high (= предписанному) — можно продолжить тем же `plan-run` без ритуала `/model`+`/effort` |
| Команда | `—` (нет single-command эквивалента) |

```
/model sonnet
/effort high
/task:plan-run 2026.07.31-SKM-LEAN P5.10
```

**Done:** **P5.9 закрыт этим заходом** (`task:plan-run`, сессия sonnet/high — Routing P5.9 =
implementation/high, точное совпадение, без перебора/недобора).

- **P5.9 🟠 Done with deviations** — флаг `--conflicts` в `plan_lint.py`: `main()` несёт
  `--conflicts` (`path` стал опциональным), `run_conflicts_check` сверяет шесть реестров-констант
  линтера с их объявлениями в `SKILL.ru.md` (статусы, 16 полей item'а, формы `Next` — читает
  альтернацию `SEMANTIC_NEXT_RE`, не переиздаёт списком, — значения `Context` — новый реестр
  `CONTEXT_VALUES`, единственный класс без предшествующей реализации, — литералы `i18n-keep` —
  реюз `CANON_LITERALS`, — регекс-носители формы launch-block'а); каждая находка — обе стороны с
  `файл:строка`. Стandalone-раскладка деградирует (WARN + exit 0). Попутно — диагностика ПОВТОРА
  поля в теле item'а (D90): `**Поле:**`-строка внутри прозы другого поля (напр. инлайн-заметка
  `**Validation:**` в Completion Notes) молча подменяла приёмочное значение — новый ERROR с обеими
  строками. Гейт нашёл 4 такие находки на ЖИВОМ дереве, все в АРХИВНЫХ планах
  (`2026.07.07-SKM-AUDIT-004` P3.3/P6.2/P6.4, `2026.07.13-PLAN-PROTOCOL-GAP` P2.10) — точечно
  починены (вердикт «первична реализация», правка по существу, не подгонка реестра). Это диф ВНЕ
  `Files` item'а → material по status-rule → `🟠`, а не `🟢`. Регистрация: ступень в
  `packages/task/scripts/validate.sh`, `--conflicts` назван первой дешёвой командой конфликт-скана
  в `packages/task/commands/plan-audit.md` §1, новый раздел `packages/task/docs/reference/
  plan-tooling.md`. `roadmap/plan-audit-loop.md` удалён (`find … -delete`), строка перенесена в
  `roadmap/README.md` «Закрыто и удалено». Правка `plan-audit.md` потребовала
  `render-provider-commands.py --write --repair-owned` (регенерация провайдер-проекций) + ручной
  синхронизации golden-фикстуры и `docs/reference/provider-commands.md` — попутно снят
  ПРЕ-существующий дрейф Codex-адаптеров `task-design`/`task-research`/`task-review` + оба
  lock-файла (был назван P5.8 Pending Work как нетронутый там; теперь закрыт, carve-out (б)).
  `test_canon_literals.py` реюзает `I18N_KEEP_RE`/`_find_skill_ru` из `plan_lint.py` (не вторая
  копия). `validate.sh` (task) — OK, 478 тестов, `plan-lint: OK` (16 планов, 0 ошибок), `--conflicts:
  OK`. `check-translations.sh --strict` — OK. Item-коммит `5e3d65e4`. Known Deviations: диф вне
  `Files` (три архивных плана, названо выше). Pending Work: стray-упоминание `plan-audit-loop.md` в
  `roadmap/plan-design-vs-exec-status-check.md:70` (неформальная заметка, не машинная ссылка) —
  следующей содержательной правкой того файла.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
**P5 4/11 (🟡 In progress)** · P6 0/3 (⬜) · P7 0/4 (⬜). Открыты P5.10–P5.11. Следующий по
порядку — **P5.10** (`solo`, `manual`, implementation/high) → **P5.11** (D110, идёт ПОСЛЕ P5.10).

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P5.md` (ТЗ P5.10 и далее) · `plan.md` §3
Routing · `roadmap.md` (карта батчей).

**Open risks:**

- Прежние (не изменились этим заходом): supply-chain находка §3.1 живая до закрытия P5.10 · гейт
  триажа красен по конструкции (D109) · пинованный внешний источник может исчезнуть · ветка (C) OQ-6 не
  проверена данными · преэкзистентный HTTP 404 `oss-dev/to-issues` · U1/U2 `[UNVERIFIED]`, остаток риска
  D106, контракт P4.1 пинован на `06fefc87`.
- **Чужой дифф в рабочем дереве** (этим заходом не тронут): удалённый `RESEARCH/AUDIT-loqum-findings.md`;
  untracked `.swissknife/` и `audits/`.
- `scripts/test-provider-docs.py` несёт 2 известных FAIL (устаревшие утверждённые хеши манифеста) —
  адрес P6.3, не трогать здесь.
- P5.3 Pending Work: унификация четырёх самописных парсеров `*.env.ini` — вне Scope, уходит в
  `roadmap/` при подтверждении владельцем.
- Окружной дефект `codex exec -s read-only` (bwrap/AppArmor, обход `--dangerously-bypass-approvals-
  and-sandbox`) остаётся в силе для будущих item'ов, зовущих `codex exec` в sandboxed режиме.
- P5.5 Pending Work (не изменилось этим заходом): `codex plugin update` отдельным тестом не покрыт.
- **Закрыто этим заходом (было открыто с P5.8):** `packages/task/adapters/codex/
  {provider-artifacts.lock.json, publication-lock.json}` и Codex-артефакты `task-design`/
  `task-research`/`task-review` ресинхронизированы (`render-provider-commands.py --write
  --repair-owned`, попутный эффект правки `plan-audit.md` в P5.9). `render-provider-commands.py`
  по-прежнему не несёт per-artifact `--only`-селектора — не критично, раз whole-catalog regen уже
  штатно применяется на каждой правке команды.
- **Новое (P5.9):** стray-упоминание `plan-audit-loop.md` в прозе
  `roadmap/plan-design-vs-exec-status-check.md:70` — не машинная ссылка, вне `Files` P5.9, чинится
  следующей содержательной правкой того файла (см. P5.9 Pending Work).

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений (см. предыдущий handoff): унификация парсеров `*.env.ini` (P5.3
  Pending Work); `codex plugin update` round-trip (P5.5 Pending Work) — обе решением владельца.
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец протокола).
