# HANDOFF — 2026-07-02 — after P1.10

**Next:** план закрыт (обе фазы терминальны; допуск «план закрыт» в Next узаконен
этой же волной, D9). Сессионной работы по SKM-MASTER-003 нет. Следующее по
экосистеме — календарные хвосты SKM-MASTER-002 (его handoff.md) и живая обкатка
plan-системы владельцем.
**Done:** план целиком, 19/19 items (16 🟢 + 3 🟠). P1 — plan-система per-project:
plansDirectory тремя слоями (harness `hooks --plans-dir` → maind провижионеры
`plans-dir`/`plans-doc` → skiller integrate `_block_plans_dir`), plans/ACTIVE.md как
active-указатель (ведут plan-design/plan-close, валидирует plan-lint root-режимом
вместе с черновиками), конвенция hashed-блоком `maind:plan-conventions` в CLAUDE.md,
мост plan mode → протокол `plan-design from-draft`, цикл «фаза → handoff → /clear»
в plan-exec/plan-close, скилл plan-protocol расширен и вошёл девятым в CORE
(705/750), пилот azguard end-to-end 7/7 зелёный. P2 — 9 хвостов рецензии (см. Phase
Handoff P2.md). Field-feedback пилота F1/F2/F4 починен пост-волной (D9). Closer:
registry · budget --check-core 705/750 · update-upstreams --check 0 failed ·
bucket-audit 9/9 CORE resident · все 5 validate.sh + core/tests зелёные ·
plan-lint plans/ 0/0.
**Remaining:** (всё вне этого плана)
- живая обкатка владельцем: первое планирование в plan mode → черновик ложится в
  plans/ (эффект plansDirectory, headless не проверяется) → `/task:plan-design
  from-draft <файл>`; артефакты пилота в azguard не закоммичены — принять/откатить.
- фан-аут plan-системы на ~17 проектов: `maind sync --only plans-dir,plans-doc`
  после зелёной обкатки (D2).
- календарные хвосты SKM-MASTER-002: P8.5 (пин baseline, ≥2026-07-09/16) → P8.2 →
  P8.3 → P8.4; P7.4 dead-pass — разблокирован P2.2, учесть фактический периметр
  resident-канала (122 скилла, не только CORE).
- deferred: F3 — honest `changed` у провижионера plans-dir (нужен stdout из
  run_capability); триггерные T3/T6б/T6в (D6/D7); T10/T11 — владельцу (D8).
**Sources of truth:** plans/SKM-MASTER-003/plan.md · phases/P1.md, P2.md (Known
Deviations 🟠-item'ов — фактический периметр) · скилл plan-protocol (SSOT схем) ·
packages/task/scripts/plan-lint.py · packages/skiller/configs/core-policy.json
(синхронно с config.py::_load_core_policy) · журнал волны wf_f2230ded-396.
**Open risks:** эффект plansDirectory в живом plan mode не проверен (эмуляция,
Pending Work P1.10); CORE-резидент 705/750 — близко к потолку, следующий CORE-скилл
потребует поднять target или ужать description'ы; периметр resident-канала
bucket-audit шире CORE (осознанно, но до P7.4 перепроверить); рабочее дерево azguard
несёт незакоммиченные пилотные артефакты (.claude/settings.json, CLAUDE.md новый,
plans/PILOT-AZG, docs/dev/README.md) — решение владельца.
**Workarounds/Deferred/Open questions:**
- workarounds: шаг plan mode пилота — эмуляция черновика (headless plan mode нет);
  удаление черновика в пилоте — mv в scratchpad вместо rm (deny_hard-хук).
- deferred: F3 (JSON changed plans-dir); доработка хука run-report для per-skill
  сигнала в SCHEMA=2 (если владелец захочет усилить bucket-audit трендом — отдельный
  item, см. Known Deviations P2.2).
- open_questions: T10 (merge-вердикты псевдо-overlap) и T11 (chatom .gitignore) —
  владельцу (D8).
