# plans/ — исполняемые мастер-планы монорепо

Каталог мастер-планов по протоколу `plan-protocol`: «сильная» модель (opus) проектирует план,
«дешёвая» (sonnet/haiku) исполняет его items без доступа к чату планирования. Каждый план —
каталог `plans/<PLAN-ID>/` с тремя видами файлов: `plan.md` (Meta, правила, Status Board, логи),
`phases/Pn.md` (по файлу на фазу: контекст + items + phase handoff), `handoff.md`
(rolling-указатель «где мы», перезаписывается).

- **Протокол (SSOT):** скилл `packages/skiller/skills/general/plan-protocol/` — схемы,
  6 канонических статусов, routing-матрица, эскалация; шаблоны — его `snippets/`.
- **Команды:** `/task:plan-design` · `/task:plan-exec` · `/task:plan-close` · `/task:plan-audit`.
- **Валидатор:** `python3 packages/task/scripts/plan-lint.py plans/<PLAN-ID>` (или `plans/` —
  все планы разом); exit 0 = формат чист. Из plugin-контекста команды зовут его через
  `${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py`; нет переменной — используй прямой путь выше.

**ПРАВИЛО MD-only:** источник истины плана — только Markdown с жёсткими маркерами.
Любой JSON — производный артефакт (`plan-lint --json`), руками не правится и не хранится.

## Очередь планов и владение поверхностями

**Обновлено:** 2026-07-25 · Регистр межплановой очереди. Носители решения —
`2026.07.18-FOREMAN` D49/D50 · `2026.07.25-ECO-OPT` D10/D11/D12 ·
`2026.07.24-AGENT-RELIABILITY` D50. `ACTIVE.md` называет текущий план, эта
секция — порядок и границы остальных.

| План | Статус | Позиция в очереди |
|:--|:--|:--|
| `2026.07.24-AGENT-RELIABILITY` | 🟡 ACTIVE, 0/22 | **Идёт первым.** `G-EXEC` выдан (его D50), старт с P0.1 |
| `2026.07.25-ECO-OPT` | 🟡 0/16 | Частично параллельно (см. окна ниже) |
| `2026.07.18-FOREMAN` | 🟡 9/33 | После терминальных P1 и P2 AGENT-RELIABILITY |
| `2026.07.19-DUAL-PROVIDER` | 🟠 терминален | Не исполняется. Его выход — **low-trust вход** (AGENT-RELIABILITY D54) |

### Почему такой порядок

AGENT-RELIABILITY чинит саму машину доставки и исполнения: единый semantic
source, uniqueness-гейт, версионирование генерируемых артефактов, diff-scope
guard, компилятор контракта задач. Остальные планы пишут именно в эти
поверхности — выполненное раньше проходит через незапечатанный генератор
(ровно тот механизм, что породил 30 рукописных root-адаптеров одним коммитом
`e8f5b477`) и переделывается.

### Владение поверхностями

| Поверхность | Владелец правки | Кто ждёт |
|:--|:--|:--|
| `packages/task` канон + скилл `plan-protocol` | AGENT-RELIABILITY **P2.2** (единственный, `2.11.0→2.12.0`), затем P2.3 | ECO-OPT P1.2/P2.2/P7.1 · FOREMAN P1.5 |
| `skiller` publication/registry/оба marketplace | AGENT-RELIABILITY **P1.2/P1.3/P1.5**, затем P2.2 | ECO-OPT P3.1/P6/P7 · FOREMAN P6 |
| `harness` provider/permissions/хуки | AGENT-RELIABILITY **P1.3** | ECO-OPT P6.1 · FOREMAN P3 |
| `maind` | **ECO-OPT P3.2 → P4** (последовательно внутри плана) | FOREMAN P4 |

### Параллельные окна ECO-OPT

- **Сразу, параллельно AGENT-RELIABILITY:** P1.1, P2.1, P3.3, P4.1–P4.3, P5.1–P5.2
  (не касаются четырёх поверхностей выше).
- **После терминальной P1 AGENT-RELIABILITY:** P3.1, P6, P7.
- **После терминальной P2:** P1.2, P2.2, P7.1 (cross-plan gate в §2 ECO-OPT).

### Разведение супервизора (решение владельца 2026-07-25)

AGENT-RELIABILITY P2.2/P2.3/P3.1 и FOREMAN P2/P5 строили одну функцию —
супервизор исполнения. Artifex (FOREMAN) переопределён как **тонкая обвязка**:
CLI-запуск headless-сессий и Telegram-эскалация остаются, а решения
next/retry/escalate потребляются из контрактов `execution-state-machine-v1`,
`risk-review-loop-budget-v1`, `unified-agent-trace-v1`. Пере-скоуп его P2/P5 —
отдельным design-заходом, только после заморозки этих контрактов.
