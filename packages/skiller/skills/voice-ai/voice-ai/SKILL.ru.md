> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: voice-ai
bucket: voice-ai
version: 0.1.0
description: Проектирование голосовых AI-агентов реального времени: транспорт (WebRTC media + WebSocket control), turn detection (VAD + семантический EOU), barge-in под 500ms, латентность под 800ms, оркестрация STT→LLM→TTS, session state-machine, RU-стек и offline-fallback. Активируй при проектировании voice-агента/IVR/колл-бота, выборе транспорта голоса, настройке перебивания/turn-taking, бюджете латентности речи, подборе речевого стека под RU и 152-ФЗ.
risk: draft
persona: architect
tags: [voice, realtime, webrtc, stt, tts, vad, barge-in, latency, russian-stack]
level: ""
requires: []
produces_for: []
outputs: ["docs/03_Dev/Voice_Architecture.md"]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Voice AI (голосовые агенты реального времени)

Применять когда: задача на проектирование голосового AI-агента реального времени —
телефонный бот / IVR-замена / веб-виджет с голосом, разговорный ассистент, диктовка с
реакцией. Скилл про **архитектуру голосового контура** (транспорт, turn-taking, перебивание,
бюджет латентности, оркестрация STT→LLM→TTS, состояние сессии) и **подбор стека под RU**.
Не про синтез отдельного аудио и не про офлайн-транскрибацию файлов (там нет реального времени).

---

## Принцип

Голосовой агент — это **бюджет латентности под жёстким потолком** плюс **корректный turn-taking**.
Пользователь ощущает не «умность» модели, а паузу перед ответом и то, можно ли перебить.
Всё проектирование крутится вокруг двух чисел: задержка «конец речи → первый звук ответа»
и время реакции на перебивание. Каждый компонент выбирается так, чтобы уложиться в эти два числа.

---

## Компоненты голосового контура

### 1. Media-транспорт (звук)

**WebRTC** для media-пути user↔media-слой — mainstream 2025-2026 (LiveKit, Retell, Vapi, Pipecat).
Причины: кодек Opus с FEC (устойчив к потере пакетов), нет head-of-line blocking как в TCP,
джиттер-буфер под низкую задержку. Порядок: браузер/мобайл → SFU (WebRTC) → агент-узел.

- Клиент шлёт **малые фреймы** (20-40 мс PCM/Opus), НЕ батчит крупно — иначе +латентность.
- Джиттер-буфер держать компактным (дефолтные профили LiveKit обычно ок); раздутый буфер = задержка.
- Телефония: SIP-шлюз перед SFU (звонок → media-слой), тот же контур дальше.

### 2. Control-транспорт (события/типизированные команды)

**WebSocket** (или gRPC) для control/events backend↔модель — типизированные события, не сырой звук:
`speech_started`/`speech_stopped`, токены ответа, function-calls, старт/стоп TTS. Это даёт узлу
видеть каждый байт → логировать, редактировать (PII), инжектить промпт, соблюдать комплаенс.
Плата: +80-150 мс в одном регионе против чистого WebRTC (TCP-ретрансмиты) — приемлемо ради контроля.

**Итог: WebRTC для media + WebSocket для control — не либо/либо, а вместе.**

### 3. Turn detection (кто сейчас говорит / договорил ли пользователь)

Одной VAD НЕДОСТАТОЧНО. Три слоя, комбинируй:

| Слой | Что делает | Когда мало |
|:--|:--|:--|
| **Классическая VAD** (энергетическая) | реагирует по громкости/тишине: threshold, prefix_padding, silence_duration | быстро, но режет посреди фразы, не понимает «ну…», незаконченную мысль |
| **Семантический EOU** (semantic VAD, end-of-utterance) | классификатор «договорил / нет» по СМЫСЛУ (волна + языковые признаки) | требует модели; напр. Pipecat smart-turn-v2 — мультиязычный, RU в наборе, ~410 мс на 16-ядерном CPU |
| **LLM-side detection** | модель сама эмитит speech_started/stopped и решает границу (напр. Realtime semantic_vad, eagerness low/med/high) | завязано на конкретный API |

**Правило порога:** закрывать ход по тишине И семантической завершённости — не только по паузе.
`silence_duration` короткий (300-500 мс) = быстрее, но риск преждевременного обрезания; семантика
это страхует. Тюнинг eagerness/threshold — под шумовой профиль и темп речи пользователя.

### 4. Barge-in (перебивание)

Реакция на перебивание — **под 500 мс** от начала речи пользователя. При детекте:
**немедленный стоп TTS**, флаш забуференного аудио в SFU/агенте, переход в listening.

- **Отличать backchannel от перехвата.** «ага», «окей», «угу» на фоне речи агента — это
  подтверждение (backchannel), НЕ повод затыкать TTS. Перехват — это попытка забрать ход.
  Различай по **word-count** (1-2 коротких слова → скорее backchannel) + семантике (вопрос/
  команда/отрицание → перехват). Порог не только по громкости.
- Если API поддерживает — включить `interrupt_response=true` (модель сама глушит вывод на речь юзера).

### 5. Оркестрация STT→LLM→TTS

Единый gateway абстрагирует движки: `ASR` / `LLM` / `TTS` за интерфейсом, роутинг по тенанту/региону.

- **Стримингом, не по завершении.** STT отдаёт partial+final гипотезы в одном соединении; каждый
  значимый partial может триггерить LLM; ответ LLM токенами → в стриминговый TTS чанками.
- **Не ждать полного финала**, где можно начать раньше — это главный рычаг латентности.
- Function-calling/tools — на control-канале; долгий tool не должен молча висеть (филлер/earcon).

### 6. Session state-machine

Состояние сессии — явный автомат, иначе перебивание и turn-taking разъезжаются:

```
idle → listening → thinking → speaking → (barge-in) → listening
```

- `idle` — нет активной реплики; `listening` — принимаем речь юзера (VAD/EOU активны);
  `thinking` — LLM генерирует (можно короткий филлер, если >X мс); `speaking` — играет TTS,
  barge-in-детектор активен; перебивание из `speaking` → мгновенно `listening` (стоп TTS).
- Переходы — по событиям control-канала, не по таймерам «на глаз».
- Ограничения провайдера учитывать в автомате: напр. Yandex SpeechKit streaming — **сессия ≤5 мин**
  на поток (жёстко, не меняется) → ротация STT-сессии без разрыва разговора.

### 7. Latency (КРИТИЧНО — потолок проектирования)

Цель сквозной задержки «пользователь договорил → первый звук ответа» — **под 800 мс**.

| Планка | Диапазон | Статус |
|:--|:--|:--|
| **premium** | < 500 мс | лучшие деплои 2026 (WebRTC + semantic VAD + стриминг) |
| **good** | 500-800 мс | целевой прод |
| **legacy/IVR** | ~1200 мс | **устаревшая** планка старых IVR — помечать как legacy, НЕ брать за цель |

> ⚠️ **НЕ проектируй под 1200 мс как целевую** — это планка legacy-IVR. Современная цель — под 800 мс,
> premium — под 500 мс.

Разбивка бюджета (ориентир, интра-регион):

| Стадия | Ориентир |
|:--|:--|
| Захват + клиент (encode, джиттер-буфер) | ~50-150 мс |
| Сеть до SFU/backend | ~20-100 мс |
| VAD / семантический turn-detect (до решения «договорил»/перебивание) | < 150-250 мс |
| Реакция модели (событие + первые токены) + старт/стоп TTS | ~150-300 мс |

Рычаги: WebRTC (не WebSocket на media), малые фреймы, стриминг STT+TTS, короткий silence_duration
со страховкой семантикой, semantic VAD с eagerness=high для агрессивного barge-in.

---

## Примеры

### RU-стек (152-ФЗ, data-residency)

Online-first в РФ-ЦОД + offline-fallback, персональные данные не покидают РФ:

- **STT/TTS online:** Yandex **SpeechKit** (streaming gRPC v3, partial+final, сессия ≤5 мин,
  neural-голоса) ИЛИ Sber **SaluteSpeech**. On-prem вариант — **SpeechKit Hybrid** (те же модели,
  ноль внешней связности) для air-gapped/строгого комплаенса.
- **LLM:** **YandexGPT** (Yandex AI Studio, есть готовый voice-agent-пайплайн с памятью/tools) ИЛИ
  **GigaChat** (Sber). Fallback — self-hosted (Qwen/Llama-совместимые) на своей РФ-инфре.
- **Offline-fallback (нет внешних API / строгий local):** STT — **Whisper** (large-v3/turbo; слабее
  на RU-телефонии и узкой полосе, чем cloud); VAD/диаризация — **pyannote.audio** (кэш моделей
  локально, `HF_HUB_OFFLINE=1`); TTS — RU neural (**Piper/VITS**, качество ниже cloud); LLM — Llama
  offline. Это полный контур STT+диаризация+LLM+TTS без внешних вызовов.

**Ремарка 152-ФЗ / data-residency (обязательна в дизайне):** персональные данные граждан РФ —
хранение в РФ. Паттерн: per-tenant `region=RU` → все вызовы/бакеты/логи в РФ-ЦОД (Yandex ru-central1
или свой ЦОД); **НЕТ cross-region fallback** — при `region=RU` офлайн-фолбэк ТОЛЬКО локальный
(Whisper+pyannote+local LLM), не EU/US-облако. Отдельно: законное согласие на запись/обработку речи,
сегрегированные логи/аналитика/эмбеддинги в РФ-only инфре.

### Polyglot SDK (кросс-язычный прод, без жёсткого RU-требования)

- **Media/runtime:** LiveKit (SFU + LiveKit Agents) — WebRTC для user-media, агент-узел читает треки.
- **Мозг:** OpenAI **Realtime** (speech-to-speech) по WebSocket из backend; turn_detection =
  `semantic_vad`, `create_response=true` + `interrupt_response=true` для barge-in.
- **Turn-detection локально (доп. контроль):** Pipecat **smart-turn-v2** или LiveKit turn-detector на
  PCM — семантический EOU, чтобы не зависеть только от VAD провайдера.
- **TTS-альтернатива:** ElevenLabs/свой TTS, если нужен иной голос, — стрим обратно в LiveKit-трек.

---

## Риски / trade-offs

| Риск | Суть | Смягчение |
|:--|:--|:--|
| **WebSocket на media** | TCP head-of-line, +латентность, столлы на потере пакетов | WebRTC/Opus на media; WebSocket ТОЛЬКО на control |
| **Только VAD** | режет посреди фразы, ложные turn-end на паузах/«ну…» | + семантический EOU; порог по тишине И смыслу |
| **Backchannel как перехват** | «ага» глушит TTS, разговор рвётся | word-count + семантика; не только громкость |
| **Латентность 1200 мс как цель** | ощущается как IVR, не как разговор | цель < 800 мс, premium < 500; 1200 = legacy |
| **Слепой backend** | нет логов/редактирования PII/комплаенса | control-канал через свой узел (видит каждый байт) |
| **Session-лимиты провайдера** | напр. SpeechKit ≤5 мин/поток → обрыв на длинном звонке | ротация сессии в автомате без разрыва разговора |
| **Offline-fallback на RU** | Whisper/RU-TTS слабее cloud на телефонии | ожидания вниз; premium-качество — только online cloud |
| **Cross-region fallback при 152-ФЗ** | утечка ПД за пределы РФ при фолбэке | при region=RU фолбэк ТОЛЬКО локальный, не EU/US |

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Гонять media по WebSocket ради «простоты» (латентность/столлы) — media = WebRTC.
- Полагаться на одну энергетическую VAD для turn-taking.
- Глушить TTS на любой звук пользователя (backchannel ≠ перехват).
- Брать 1200 мс за целевую латентность (это legacy-IVR-планка).
- При `region=RU` фолбэкать на EU/US STT/TTS/LLM — только локальный офлайн.
- Проектировать без явного session state-machine (перебивание разъедется).

---

## Чеклист качества

- [ ] Транспорт разделён: media = WebRTC, control/events = WebSocket (типизированные).
- [ ] Turn detection многослойный: VAD + семантический EOU; порог по тишине И завершённости.
- [ ] Barge-in под 500 мс: мгновенный стоп TTS → listening; backchannel отличается от перехвата (word-count + семантика).
- [ ] Задан бюджет латентности с целью под 800 мс (premium под 500); 1200 мс НЕ используется как цель.
- [ ] Оркестрация стримингом (partial STT → LLM токены → TTS чанки), а не по полному финалу.
- [ ] Явный session state-machine idle→listening→thinking→speaking с barge-in-переходом.
- [ ] Учтены лимиты провайдера (напр. SpeechKit ≤5 мин/сессия — ротация).
- [ ] RU-кейс: стек Yandex/Sber, offline-fallback, ремарка 152-ФЗ (region=RU, без cross-region fallback).

---

## Ссылки

- OpenAI Realtime VAD/turn-detection: https://developers.openai.com/api/docs/guides/realtime-vad
- Pipecat smart-turn-v2 (семантический EOU, мультиязычный, RU): https://huggingface.co/pipecat-ai/smart-turn-v2
- Yandex SpeechKit STT (streaming gRPC v3): https://aistudio.yandex.ru/docs/en/speechkit/stt/
- Yandex AI Speech (voice-agent-пайплайн): https://aistudio.yandex.ru/en/ai-speech
- WhisperX + pyannote offline: https://github.com/m-bain/whisperX

## Связанные скиллы

- `architect/api-design` — WebSocket/gRPC control-контракт голосового контура (события, function-calls).
- `architect/architecture` — общий контекст, где голосовой контур — один из контейнеров системы.
- `architect/security-design` — auth медиа-сессий, редактирование PII на control-канале.
- `architect/legal-compliance` — 152-ФЗ / согласие на запись, data-residency в деталях.
