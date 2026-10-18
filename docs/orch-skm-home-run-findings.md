# Run findings of the SKM-HOME plan (one machine home, project layer in the workspace)

Observer notes of the conductor runs of the plan (machine A). Item ids are written without plan numbers (hygiene).
Numbers: P1 5 runs/rounds incl. a manual stop, P2 batch 18m55s for three items, P3 batch ~1h50m for five items,
P4.2 6m. Group reviews by `codex/gpt-6.1-sol/xhigh` (P1.1 by hand, P3 by the conductor): 4 Major each, fixed in a followup.

# observer-plan7 findings

- F1 (fixed ca32a27ad): bridges/planner-orch brief падал для плана в workspace (`artifacts_dir` relative_to чекаута). Теперь поле опускается, orch берёт fallback.
- F2 (open): `op_research` (bridges/planner-orch/worksource.py ~523) — тот же relative_to для плана вне чекаута. Заметка в ideas/.
- F3: `--adopt` падает WORKTREE_DIRTY из-за чужих untracked `.swissknifeman/orch-artifacts/run-08c0.../`; без --adopt они идут как FOREIGN_KEPT. Не использовать --adopt.
- F4: P1/P2 были skeleton → нужен `planner design-done` перед run (P3, P4 — перед их запуском).
- F5: порядок P2→P1 противоречил depends_on (ideas/plan7-phase-order-vs-depends.md); владелец выбрал P1 первым.
- F6: P1.1 executor 25m05s, tokens 217431/70834; checks.1 с 09:05 (>4 мин, tests orch/aicore).
- F7 (observer mistake): записал ideas/plan7-bridge-research-outside-checkout.md в основное дерево во время run (untracked, FOREIGN_KEPT, закоммичу между пунктами). Дальше — заметки только в state/ до конца run.
- F8: checks.1 V1 красный (4m48s) → executor.2 (круг исправления). CHECK_CHANGED_TREE засчитал мой ideas-файл (следствие F7). INPUT_REBUILT: план изменился во время пункта.
- F9: --adopt блокируют untracked orch-artifacts прежних run (чужие run-08c0..., cnd-...c569c8): перенёс mv в state/foreign. Предложение: adopt должен игнорировать .swissknifeman/orch-artifacts/** (записи самого conductor).
- P1.1 commit ee71f6423 (conduct не запустил ревью: strategy single/rules пропустила) → ручное ревью codex xhigh в /tmp/claude-1000/-home-vostrikov-projects-packages-swissknifeman/c060bfc0-d2fd-45a3-b5f1-0fd4e87f8d05/scratchpad/verdict1.md

## Анализ времени P1.1 (08:29 → ~09:50, ≈80 мин на один пункт)
| Статья | Мин | Причина | Что менять |
|:--|:--|:--|:--|
| Старт: skeleton P2, зависимость P2→P1, баг моста brief, WORKTREE_DIRTY на --adopt | ~10 | design-done не был сделан; bridge не знал плана вне чекаута; untracked artifacts блокируют adopt | F1,F4,F9: перед run — preflight `design-done` всех фаз плана и проверка dry-run `brief`; adopt игнорирует orch-artifacts |
| Executor.1 | 25 | объём пункта большой (52 файла) | нормально; делить P1.1 на 2 пункта (код / потребители) в будущих планах |
| Красные V1 из-за базы (drift CLAUDE.md, public-hygiene) ×3 круга + blocked + reopen + adopt-run | ~25 | старые красные проверки ВНЕ пункта: пункт нельзя закрыть, executor тратит круги | F10: preflight «V1 на чистом HEAD» ДО старта run; красная база чинится отдельным коммитом заранее |
| Ручное ревью codex + followup (ревью не запустилось само) | 25+ | conduct не сделал групповое ревью (adopt-run); executor followup сам гонял `affected-tests --no-cache` 601 с (10 мин) и conductor потом повторит | F11: в followup/прompt executor — не запускать полный V1, это делает conductor; ревью после adopt-run запускать автоматически |
| Мои потери | ~10 | заметка в дерево во время run (F7), стыки с reopen | см. правила: заметки только в state/ |

F10: добавить в orch preflight (`conduct run --dry-run`) прогон V1 на чистом HEAD, если run стартует с чистым деревом, и отказ `BASELINE_RED` с перечнем (экономит 3 круга и ручной блок).
F11: executor.1 в followup 601 с (86% шага) — полный `affected-tests --no-cache` внутри роли; conductor делает те же проверки заново. Дубль.
- F12: opts-*2.json с rules для executor (не гонять полный V1) — использовать для следующих run.
- F13: followup input с acceptance expect:observed + текстовой procedure → checks.1 red за 0с и лишний executor.2; run остановлен SIGTERM по PID, V1 прогнан на хосте (зелёный), правки закоммичены вручную. Для followup писать acceptance как cd/CMD (как делает conductor).
- P1.2: auto-mode classifier заблокировал 'config migrate-home' (Irreversible Local Destruction); бэкап ~/skm-backup-2026-10-18/skm-machine.tgz готов; команда за владельцем. design-done P3,P4 выполнен.
- F14: committed orch-artifacts плана вне чекаута содержат PLANn.Pm → public-hygiene красный на базе следующего пункта; GENERATED_RECORD_DIRS в hygiene (commit). Закрывающий V1 фазы P1 (tier all) теперь зелёный по этому пункту.
- F15: OPTIONS_INVALID оставляет claim пунктов (ITEM_OWNED у следующего run) → release --all вручную; orch должен отпускать claim при OPTIONS_INVALID.
- P2 закрыт: P2.1 b2af857e6, P2.2 17e3177e5, P2.3 ef2497626; run 18м55с; tier all зелёный. Playwright GUI-форм не запускался — отчёт владельцу.
- P3: коммиты P3.1..P3.5 (3acec1327 последний), run 12:56→; групповое ревью codex xhigh 446с: 0 Blocker, 4 Major, 3 Minor (копия .swissknifeman/state/observer-plan7/p3-group-review-1.md) → followup.
- P3 закрыт: ревью-фикс 2ab25f304 → cherry-pick 8be5d7dd3 (run в worktree из-за чужих правок в дереве, F16: две сессии в одном дереве); tier all P3 зелёный
- F17: run в worktree: register ищет evidence в привязанном чекауте (main) → REGISTER_REFUSED; commit-мост закоммитил в main только записи run, файлы пункта остались в worktree — перенёс вручную (5 doc-файлов, коммит docs(skm-home)).
- P4.1 (6 проектов): azguard, billium(d7b28ee), chatom, commerz, corex, sockit — project migrate, doctor без fail, planner plans совпал со снимком; бэкап ~/skm-backup-2026-10-18/projects-swissknifeman-dirs.tgz; vaulter и хаб остаются (vaulter ждёт сигнала владельца). project.env-snippet warn: нужен 'aicore shell-env install' (изменение ~/.bashrc, за владельцем).
- MIGRATION-HOST-B.md: добавлено правило «project migrate первым» и рецепт слияния events/deliveries/cursors (урок vaulter).
