# Сквозная мультипровайдерность и быстрый выход в поле

**Дата:** 2026-08-08  
**Потребитель:** весь `2026.08.07-PLAN-ECONOMY`, особенно P0.1, P2.8, P3.7 и P6.1–P6.3  
**Основание:** два последовательных уточнения владельца 2026-08-08.

## 1. Один shared contract, независимые provider certifications

План не проектирует «архитектуру Codex, которую потом портируют». Он проектирует shared semantics
и явный adapter seam. Текущий provider обязан доказать только свою строку матрицы:

| Слой | Сейчас | Позже при подключении Claude |
|:--|:--|:--|
| shared contracts/core | проектирует Codex; provider ids/raw events запрещены вне seams | не перепроектируется; изменения только через новый D# при дефекте общей границы |
| Codex adapter/projection | реализуется и получает `verified` на Codex evidence | остаётся отдельной строкой |
| Claude adapter/projection | `pending-provider`, без speculative code и ложного green | Claude проверяет raw contract, добавляет/чинит только свой adapter и переводит строку в `verified` |

Допустимые состояния provider row: `verified`, `pending-provider`, `failed`. `pending-provider` не
блокирует shared core или active Codex rollout, но и не считается паритетом. Shared schema не
содержит union всех сырых полей провайдеров: каждый adapter нормализует свой raw contract.

Provider-specific implementation surface закрыт: thin raw-usage/runtime adapters и generated
command/skill projections с locks. Все Python reducers/gates/migration tools, schemas, canonical
commands, skills и rubric assets имеют один shared SSOT. Если item не касается raw provider API или
проекции, ему не нужна provider matrix: shared test доказывает его для всех providers.

## 2. Проверка плана по фазам

| Фаза | Provider-neutral основание | Проверяем сейчас |
|:--|:--|:--|
| P0 | canonical token probe/qualified calibration target | Codex adapter + небольшой реальный corpus |
| P1–P2 | reader/carrier contracts не называют provider UI, auth или raw events | shared tests и self-hosting этого реального плана |
| P3 | deterministic gates работают по contracts/artifacts, не по активной модели | shared tests + read-only canary на реальных project inputs |
| P4–P5 | return/decision records несут model/provider provenance как данные, но policy не ветвится по бренду | shared reducer/policy tests; current Codex judgement path там, где модель нужна |
| P6 | canonical commands — SSOT; provider projections аддитивны и имеют независимые locks/tests | canonical + Codex projection; Claude row остаётся `pending-provider` |

Исторические Claude evidence и authoring provenance не являются нарушением: дефект возникает только
когда Claude-specific форма становится общей схемой или гейтом active пути.

## 3. Бюджет ранней калибровки

P0.1 не должен повторять дорогие `3 × N` вызовы для доказательства архитектуры. Active v2 использует
bounded pilot corpus: **8 samples из 8 разных реальных файлов**, каждый payload ≤16 KiB,
суммарный provider input ≤128 KiB. Минимум три samples берутся из трёх dense-файлов, минимум два
малых файла идут целиком, а все пять классов получают ненулевое покрытие. Это больше шести
параметров fitter (пять ставок + overhead), но не претендует на статистическую полноту флота.

Контроли wrapper выполняются на границах коротких batch, а не A/A′ вокруг каждого файла:

1. control с пустой payload;
2. не более трёх payload probes;
3. следующий control; соседние controls образуют bracket для payload между ними;
4. drift выше δ отбраковывает bracket целиком, а не маскируется усреднением.

Для восьми samples это максимум 12 provider calls при зелёных контролях вместо 24. Каждый sample
несёт full-source hash, byte range и собственный hash. Neutral core оперирует
`input_tokens_total`; control schedule — свойство protocol version, не Codex adapter.
Acceptance остаётся строгой на измеренном corpus: dense ≥3, `bound.violations == 0`, p95 ≤1.6,
qualified target один. Полные source-файлы проходят offline classifier/estimate canary без provider
calls. Расширение корпуса после полевых находок — обычная новая generated калибровка того же target;
оно не требует redesign, пока neutral schema и classifier не меняются.

## 4. Ранний field loop

До широкой раскатки вводятся два дешёвых, неразрушающих canary:

- P2.8 self-hosts текущий реальный план — это первая вертикальная проверка shared carriers;
- P3.7 прогоняет новые contracts/gates на текущем layout-v2 плане и на временной dry-run проекции
  одного реального fleet-плана; чужой репозиторий не изменяется.

Canary проверяет active Codex/provider path только там, где модель вообще участвует; детерминированные
гейты проверяются provider-neutral. Найденный локальный adapter/fixture defect чинится вперёд в
владеющем item. Изменение shared public contract требует D#; остальное не переоткрывает дизайн.

## 5. Вердикт пересмотра

Тяжёлую cross-provider матрицу до field loop план не требует. Надёжная основа — это стабильные
shared schemas, fail-closed adapter boundary, qualified evidence и отсутствие ложного green для
непроверенного provider. Надёжность не означает заранее реализовать или прогнать все адаптеры.

## Проверка (verification status)

- RAG: — (решение владельца + repo-grounded архитектура provider projections/locks и текущие фазы).
- Непроверено → ПОВТОРНЫЙ ПРОХОД: Claude raw contracts — проверяет Claude при подключении; не
  load-bearing сейчас.
- Обходки/[POSSIBLE-DEFECT]: —.
