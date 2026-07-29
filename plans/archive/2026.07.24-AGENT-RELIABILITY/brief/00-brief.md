# Brief — 2026.07.24-AGENT-RELIABILITY

## Запрос владельца

Подготовить план улучшения `swissknifeman`, используя:

1. аудит Perplexity `swissknifeman-audit.md`, принимая только полезные и
   доказанные выводы;
2. самостоятельную оценку пакета;
3. телеметрию фактической работы за последние 3–4 дня только по планам,
   исполнявшимся в `azguard`, `insiders`, `dterema`, `swissknifeman`;
4. Perplexity Web и собственную актуальную документацию Codex;
5. отдельный анализ раздублированных skills и нарушения SSOT.

Полевой симптом сформулирован владельцем однозначно: ни одна задача не была
сдана с первого раза без ошибок; требования забывались; процесс
останавливался без нужды; простые задачи уходили в вечные regression/audit
циклы. Нужны не оправдания и не косметический backlog, а причина и решение,
которое восстанавливает возможность продолжать работу с ChatGPT/Codex.

## Обязательные результаты

- причинная модель, которая объясняет все четыре класса симптомов;
- доказательства из raw sessions, plan journals, mAInd и runtime preflight;
- отделение причин от симптомов и от неподтверждённых гипотез;
- решение SSOT для skills/tasks/hooks/instructions;
- конечный execution/review loop без routine остановок;
- измеримые eval/telemetry gates на реальных прошлых провалах;
- исполнимый phase/item plan с model routing, authority boundaries и DoR.

## Не входит

- исполнение FOREMAN;
- изменение внешних consumer repositories;
- fleet rollout;
- generic rewrite `core/` на основании одного внешнего аудита;
- установка новых Python runtime dependencies;
- tag/push/release без отдельного owner boundary.

## Входные дефекты и уточнения

- Указанного `/tmp/swissknifeman-audit.md` не было; файл найден как
  user-owned `tmp/swissknifeman-audit.md` в репозитории и прочитан оттуда.
- `codex doctor --json` подтверждает Codex 0.145.0, model `gpt-5.6-sol`,
  approval `Never`, filesystem `unrestricted`; live effort не экспонируется.
- Hook lifecycle dry-run не зелёный: unmanaged project target, missing Codex
  handler; Claude run-report copy stale. Это часть инцидента, не исправлено в
  design-only задаче.
