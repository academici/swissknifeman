# P3 audit reopen — 2026-08-04

Владелец потребовал выполнить `task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P3`
именно как реопен терминальной фазы по четырём шагам §3, а не как повторную детализацию.
Первым входом должен быть блок `## Audit P3 — 2026-08-04` в `phases/P3.md`.

Обязательный scope реопена:

1. связать indexed admission с точным provider adapter и bounded worker/activity port;
2. заменить synthetic readiness writer реальным preflight/probe;
3. реализовать P2→P3 manifest/hash validator с adversarial mutations;
4. восстановить pre-exec committed spec, конечные Required Reads/Files и явную
   commit→item карту;
5. устранить regression полного `packages/task/scripts/validate.sh`;
6. повторить closure gates и независимый аудит P3.

Анти-scope: frozen P1/P2 carriers не переписываются; P3.1–P3.3 и историческая семантика
P3.4 меняются только необходимыми forward fixes; P4–P6 product scope и unrelated dirty
worktree не затрагиваются.
