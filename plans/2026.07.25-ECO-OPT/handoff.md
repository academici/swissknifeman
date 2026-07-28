# HANDOFF — 2026-07-28 — after P4.2

**P4.2 закрыт `🟠 Done with deviations`**: `memory.role` (standalone|host|client, дефолт
standalone — back-compat) добавлен в `config.py` с валидацией; запрет второго писателя —
КОДОМ (`memory._daemon_argv`, `provision/service.py` `install`). Аддитивное расширение
`core.http` заголовками (`headers=None`, поведение без них байт-в-байт прежнее) несёт
`Authorization: Bearer` из `memory.secret_file`/`AGENTMEMORY_SECRET`; новый
`core.http.HTTPUnauthorizedError` различает 401 от «недоступен» в `doctor`/`health`/MCP-ветке
`_run_tool`. Настраиваемый бюджет ожидания (`MEMORY_LIGHT/HEAVY_TIMEOUT_S`, `MEMORY_RETRIES`)
с ретраями только на read-пути `export()`. LAN-стадия (ADR-0001 D80): `iii-config.yaml`
`iii-http.host` → `192.168.31.93` (LAN-адрес ТЕКУЩЕЙ машины, подтверждён владельцем в сессии —
DHCP dynamic, риск в Pending Work). Известное отклонение: item-коммит несёт дифф вне `Files`
(`packages/maind/tests/fixtures.py` — `FakeMemoryServer(secret=...)`, необходим тестам 401/
bearer, DRY вместо пяти копий двойника). Детали — `phases/P4.md` P4.2 Completion Notes /
Pending Work / Known Deviations; замер канала — `findings/P4.2-remote-link-measure.md`.

**Next:** **P4.3** — rollout на вторую машину: расширение `bootstrap-machine.sh` под
роль-осознанную ступень 5 + шесть доказательных гейтов (`maind doctor`/`health --strict`,
недоступность из-за пределов подсети LAN, единственный писатель) + `docs/deploy.md` +
`packages/maind/docs/guide/systemd.md`. `Exec = manual` (§3 Routing) — часть гейтов
исполняется оператором на ДРУГОЙ физической машине (hands-on, `plan-exec`/`plan-run` их не
прогонят); ждёт не решения, а физической раскатки. Предусловие (P3.2 терминальна) уже снято.

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — предписано Routing (rollout по готовому ADR/P4.2, решений не осталось) |
| Context | continue (/clear) — ручной item |
| Суть | Rollout второй машины в режиме client + шесть доказательных гейтов (P4.3) |

```
ЗАПУСК ВРУЧНУЮ: sonnet/medium
```
```
/model sonnet
/effort medium
/task:plan-run 2026.07.25-ECO-OPT P4.3
```

**Done:** **43/52 items терминальны** (27 🟢 · 15 🟠 · 1 ⛔ — счёт снят машинно по
`**Status:**` всех `phases/P*.md`). Закрыты фазы **P1** (1/2, 🟢), **P5** (5/6, 🟠), **P8**
(7/10, 🟠), **P9** (3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠); частично — **P3** (2/6, 🟠)
и **P4** (1/3 — P4.1 🟢, P4.2 🟠, оба терминальны; P4.3 ⬜). Вне этих фаз закрыт только P2.1.

**Remaining:** 9 items, все `⬜ Not started`: P2.2/P2.3 · P4.3 · P6.1–P6.3 · P7.1–P7.3.
Порядковые условия: P2.3 — ПОСЛЕ P6.3 (D93) и ПОСЛЕ P8.1/P8.2/P8.3 (терминальны); P6.1 — ПОСЛЕ
P9.1 (снято, терминален); P4.3 — ПОСЛЕ P4.2 (терминален, только что закрыт — ждать больше
нечего); P7.1 + P7.3 → P7.2.

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index — `P4 1/3` со статусом
`🟡 In progress`, счётчик не меняется правилом «только 🟢 в числителе» — P4.2 закрыт 🟠; §6
Update Log — запись закрытия P4.2) · `phases/P4.md` (Phase Status + P4.2 Completion Notes) ·
`findings/P4.2-remote-link-measure.md` · `packages/maind/docs/guide/memory.md` (раздел
Cross-machine режим) · машинные гейты `packages/task/scripts/plan-lint.py`,
`plans/verify-citations.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей) плюс:
(35) **Перекалибровка токенайзера `budget.py` (P3.4 Pending Work) не выполнена** — недоступен
`count_tokens`/`ANTHROPIC_API_KEY` в исполнительной песочнице; точная команда ждёт захода с
креденшелами (`findings/P3.4-tokenizer-calibration.md` §3).
(36) **`voice-ai/voice-ai/upstream.json` ломает `update-upstreams.sh --check`** (пустой `path` у
5 записей, `IsADirectoryError`) — пред-существующий дефект, сопровождение вне Scope P3.6.
(37) **LAN-адрес `iii-config.yaml` (`192.168.31.93`) — DHCP dynamic**, не статическая
резервация: при переинициализации сети хост получит другой адрес, и демон памяти перестанет
быть достижим по старому `memory.url` у клиентов, пока адрес не поправят руками (или пока не
сработает триггер `tailscale serve`, ADR-0001). Рекомендация — DHCP-резервация на хосте до
P4.3 (второй машины) либо сразу переход на `tailscale serve`.
(38) **`mcp.py`'s `maind_memory_links` не прокидывает bearer-заголовки** в свой внутренний
`memory_mod.recall` (P4.2 Pending Work п.2) — на хосте с включённым секретом эта
вспомогательная ветка получит HTTP 401 (не крашится, но не деградирует красиво); не входит в
перечисленные Scope Included три инструмента `maind_memory_store/recall/forget`, оставлено
сознательно (единственная точка врезки в `mcp.py`).
(39) **`MEMORY_LIGHT/HEAVY_TIMEOUT_S` измерены на ОДНОЙ машине** (loopback vs LAN-интерфейс без
реального сетевого прыжка, `findings/P4.2-remote-link-measure.md`) — P4.3 обязан переизмерить
на настоящей второй машине и скорректировать константы отдельным D#, если числа разойдутся.

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — roadmap-кандидат **F1** (дисциплина против класса R2, P3.3) не внесён в
`roadmap.md`; расхождение 142 vs 186 записей `flexcrm` (P3.1) не разобрано до корня;
`oss-dev/to-issues/upstream.json` — апстрим-URL вернул 404, паспорт нуждается в обновлении.
· **open questions** — нет новых этим заходом; OQ-7 закрыт (`Resolved → D80`), OQ-11 остаётся
`Decision pending` до закрытия P11.
