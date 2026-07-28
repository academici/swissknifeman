# HANDOFF — 2026-07-28 — after P4.1

**P4.1 закрыт `🟢 Done`**: `root/adr/ADR-0001-cross-machine-memory.md` фиксирует восемь принятых
владельцем решений пакета (хост — текущая машина, D80; транспорт ближайшей стадии — LAN,
`tailscale serve` на триггере; секрет — единственный предохранитель на LAN-стадии; отвергнутые
варианты и известные ограничения — девять пунктов в полном составе). Компактный вход для P4.2/P4.3 —
`findings/P4.1-memory-host-decision-packet.md`. `roadmap/cross-machine-memory.md` получил датированную
приписку (Deferred снят по существу). Детали — `phases/P4.md` P4.1 Completion Notes.

**Next:** **P4.2** — реализация remote-host режима в `packages/maind` (`memory.role`, аддитивное
расширение `core.http` заголовками, `secret_file`, bind на LAN-адрес в `iii-config.yaml`, честные
ошибки недоступности/неавторизованности). `Exec = manual` (§3 Routing) — ADR P4.1 определяет ветки
реализации, ждать больше нечего (артефакт готов).

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — реализация ядра памяти экосистемы (демон-хост + клиенты), предписано Routing |
| Context | continue (/clear) — ручной item |
| Суть | Реализация remote-host режима в maind по ADR-0001 (P4.2) |

```
ЗАПУСК ВРУЧНУЮ: sonnet/high
```
```
/task:plan-run 2026.07.25-ECO-OPT P4.2
```

**Done:** **42/52 items терминальны** (27 🟢 · 14 🟠 · 1 ⛔ — счёт снят машинно по `**Status:**`
всех `phases/P*.md`). Закрыты фазы **P1** (1/2, 🟢), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9**
(3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠); частично — **P3** (2/6, 🟠) и **P4** (1/3, 🟡).
Вне этих фаз закрыт только P2.1.

**Remaining:** 10 items, все `⬜ Not started`: P2.2/P2.3 · P4.2/P4.3 · P6.1–P6.3 · P7.1–P7.3.
Порядковые условия: P2.3 — ПОСЛЕ P6.3 (D93) и ПОСЛЕ P8.1/P8.2/P8.3 (терминальны); P6.1 — ПОСЛЕ P9.1
(снято, терминален); P4.2 → P4.3 (ADR готов, P3.2 терминален — гейт снят); P7.1 + P7.3 → P7.2.

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index — `P4 1/3 🟡`; §6 Update Log
— запись закрытия P4.1) · `phases/P4.md` (Phase Status + P4.1 Completion Notes) ·
`root/adr/ADR-0001-cross-machine-memory.md` · `findings/P4.1-memory-host-decision-packet.md` ·
`roadmap.md` (строка 62 — порядок P4.1→P4.2→P4.3) · машинные гейты
`packages/task/scripts/plan-lint.py`, `plans/verify-citations.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей) плюс:
(35) **Перекалибровка токенайзера `budget.py` (P3.4 Pending Work) не выполнена** — недоступен
`count_tokens`/`ANTHROPIC_API_KEY` в исполнительной песочнице; точная команда ждёт захода с
креденшелами (`findings/P3.4-tokenizer-calibration.md` §3).
(36) **`voice-ai/voice-ai/upstream.json` ломает `update-upstreams.sh --check`** (пустой `path` у
5 записей, `IsADirectoryError`) — пред-существующий дефект, сопровождение вне Scope P3.6.

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — roadmap-кандидат **F1** (дисциплина против класса R2, P3.3) не внесён в
`roadmap.md`; расхождение 142 vs 186 записей `flexcrm` (P3.1) не разобрано до корня;
`oss-dev/to-issues/upstream.json` — апстрим-URL вернул 404, паспорт нуждается в обновлении.
· **open questions** — нет новых этим заходом; OQ-7 закрыт (`Resolved → D80`), OQ-11 остаётся
`Decision pending` до закрытия P11.
