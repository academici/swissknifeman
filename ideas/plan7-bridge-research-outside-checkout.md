# planner-orch op_research падает для плана в workspace

- Что: `bridges/planner-orch/worksource.py` (`op_research`) считает `target.resolve().relative_to(plan.repo_root)`, а план лежит в workspace → ValueError.
- Причина: тот же допущение «план внутри чекаута», что и в brief (исправлено в ca32a27ad).
- Сейчас: не исправлено, research в PLAN7 не используется (rag.need none).
- Предложение: путь относительно plans-root плана; тест с планом в workspace-фикстуре (такой фикстуры в bridge_fixture.py нет).

# Дрейф managed-блока packages/planner/CLAUDE.md (INSTRUCTION_MANAGED_DRIFT)

- Что: коммит 448849558 правил блок `planner.plan-protocol` прямо в `CLAUDE.md`, источник `harness/configs/common/instructions/packages/planner/common.md` и хеши каталога не менял → `harness instructions check` красный → `affected-tests`/`golden check` красные у любого пункта (V1 P1.1 был заблокирован этим, 3 круга).
- Сделано: блок в CLAUDE.md возвращён к тексту источника (детали про маркер проекта потеряны, они есть в docs/workspace.md; копия правленого файла в state/observer-plan7/planner-CLAUDE.md.bak).
- Причина повторов: правка managed-блока руками; обновление источника требует ручного пересчёта хешей каталога (`INSTRUCTION_PROVENANCE_INVALID`), готовой команды нет.
- Предложение: команда `harness instructions refresh` (источник → catalog hashes → render) и pre-commit проверка `instructions check` на изменённых CLAUDE.md/AGENTS.md; `repair` сейчас отказывает без observed-hash и adjacent-backup, нужен режим «принять рендер».
