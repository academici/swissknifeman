---
name: voice-ai
bucket: voice-ai
version: 0.1.0
description: Designing realtime voice AI agents: transport (WebRTC media + WebSocket control), turn detection (VAD + semantic EOU), sub-500ms barge-in, sub-800ms latency, STT→LLM→TTS orchestration, session state-machine, RU stack and offline fallback. Activate when designing a voice agent/IVR/call-bot, choosing voice transport, tuning barge-in/turn-taking, budgeting speech latency, or picking a speech stack for RU and 152-FZ.
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

# Skill: Voice AI (realtime voice agents)

Apply when: designing a realtime voice AI agent — phone bot / IVR replacement / web voice
widget, conversational assistant, reactive dictation. This skill covers the **voice loop
architecture** (transport, turn-taking, barge-in, latency budget, STT→LLM→TTS orchestration,
session state) and **RU stack selection**. Not for one-off audio synthesis or offline file
transcription (no realtime there).

## Principle

A voice agent is a **latency budget under a hard ceiling** plus **correct turn-taking**. Users
feel the pause before the answer and whether they can interrupt — not model "smartness". Design
around two numbers: "end-of-speech → first sound of reply" latency and barge-in reaction time.
Every component is chosen to fit those two numbers.

## Voice loop components

### 1. Media transport (audio)

**WebRTC** for the user↔media-layer media path — mainstream 2025-2026 (LiveKit, Retell, Vapi,
Pipecat). Why: Opus + FEC (packet-loss tolerant), no TCP head-of-line blocking, low-latency jitter
buffer. Order: browser/mobile → SFU (WebRTC) → agent node.

- Client sends **small frames** (20-40 ms PCM/Opus), does NOT batch large — else +latency.
- Keep jitter buffer compact (LiveKit default profiles usually fine); oversized buffer = delay.
- Telephony: SIP gateway in front of SFU (call → media layer), same loop onward.

### 2. Control transport (events / typed commands)

**WebSocket** (or gRPC) for control/events backend↔model — typed events, not raw audio:
`speech_started`/`speech_stopped`, reply tokens, function-calls, TTS start/stop. Lets the node see
every byte → log, redact (PII), inject prompt, enforce compliance. Cost: +80-150 ms same-region vs
pure WebRTC (TCP retransmits) — acceptable for control.

**Result: WebRTC for media + WebSocket for control — not either/or, both together.**

### 3. Turn detection (who speaks now / did the user finish)

One VAD is NOT enough. Three layers, combine:

| Layer | Does | When insufficient |
|:--|:--|:--|
| **Classic VAD** (energy) | reacts on loudness/silence: threshold, prefix_padding, silence_duration | fast, but cuts mid-sentence, misses "uh…", incomplete thoughts |
| **Semantic EOU** (semantic VAD, end-of-utterance) | classifier "finished / not" by MEANING (waveform + language cues) | needs a model; e.g. Pipecat smart-turn-v2 — multilingual, RU included, ~410 ms on 16-core CPU |
| **LLM-side detection** | model emits speech_started/stopped, decides boundary (e.g. Realtime semantic_vad, eagerness low/med/high) | tied to a specific API |

**Threshold rule:** close the turn on silence AND semantic completeness — not on pause alone.
Short `silence_duration` (300-500 ms) = faster but risks premature cut; semantics hedge it. Tune
eagerness/threshold to noise profile and user speech tempo.

### 4. Barge-in (interruption)

Barge-in reaction — **under 500 ms** from user speech onset. On detect: **immediate TTS stop**,
flush buffered audio in SFU/agent, transition to listening.

- **Distinguish backchannel from takeover.** "uh-huh", "ok", "yeah" over agent speech = confirmation
  (backchannel), NOT a reason to stop TTS. Takeover = attempt to grab the turn. Distinguish by
  **word-count** (1-2 short words → likely backchannel) + semantics (question/command/negation →
  takeover). Not by loudness alone.
- If API supports — enable `interrupt_response=true` (model mutes output on user speech).

### 5. STT→LLM→TTS orchestration

A single gateway abstracts engines: `ASR` / `LLM` / `TTS` behind an interface, routed by tenant/region.

- **Stream, don't wait for completion.** STT emits partial+final hypotheses in one connection; each
  meaningful partial can trigger the LLM; LLM reply tokens → streaming TTS in chunks.
- **Don't wait for the full final** where you can start earlier — the main latency lever.
- Function-calling/tools on the control channel; a long tool must not hang silently (filler/earcon).

### 6. Session state-machine

Session state is an explicit machine, else barge-in and turn-taking drift apart:

```
idle → listening → thinking → speaking → (barge-in) → listening
```

- `idle` — no active turn; `listening` — accepting user speech (VAD/EOU active); `thinking` — LLM
  generating (short filler if >X ms); `speaking` — TTS playing, barge-in detector active; barge-in
  from `speaking` → instantly `listening` (stop TTS).
- Transitions driven by control-channel events, not eyeballed timers.
- Encode provider limits in the machine: e.g. Yandex SpeechKit streaming — **session ≤5 min** per
  stream (hard, immutable) → rotate STT session without breaking the conversation.

### 7. Latency (CRITICAL — the design ceiling)

Target end-to-end "user finished → first sound of reply" — **under 800 ms**.

| Tier | Range | Status |
|:--|:--|:--|
| **premium** | < 500 ms | best 2026 deploys (WebRTC + semantic VAD + streaming) |
| **good** | 500-800 ms | production target |
| **legacy/IVR** | ~1200 ms | **outdated** old-IVR bar — mark as legacy, do NOT target |

> ⚠️ **Do NOT design for 1200 ms as target** — that is the legacy-IVR bar. Modern target is under
> 800 ms, premium under 500 ms.

Budget breakdown (guide, intra-region):

| Stage | Guide |
|:--|:--|
| Capture + client (encode, jitter buffer) | ~50-150 ms |
| Network to SFU/backend | ~20-100 ms |
| VAD / semantic turn-detect (to "finished"/barge-in decision) | < 150-250 ms |
| Model reaction (event + first tokens) + TTS start/stop | ~150-300 ms |

Levers: WebRTC (not WebSocket on media), small frames, streaming STT+TTS, short silence_duration
hedged by semantics, semantic VAD with eagerness=high for aggressive barge-in.

## Examples

### RU stack (152-FZ, data residency)

Online-first in RU DCs + offline fallback, personal data never leaves RU:

- **STT/TTS online:** Yandex **SpeechKit** (streaming gRPC v3, partial+final, session ≤5 min,
  neural voices) OR Sber **SaluteSpeech**. On-prem: **SpeechKit Hybrid** (same models, zero external
  connectivity) for air-gapped/strict compliance.
- **LLM:** **YandexGPT** (Yandex AI Studio, ready voice-agent pipeline with memory/tools) OR
  **GigaChat** (Sber). Fallback — self-hosted (Qwen/Llama-compatible) on your RU infra.
- **Offline fallback (no external API / strict local):** STT — **Whisper** (large-v3/turbo; weaker on
  RU telephony/narrowband than cloud); VAD/diarization — **pyannote.audio** (models cached locally,
  `HF_HUB_OFFLINE=1`); TTS — RU neural (**Piper/VITS**, quality below cloud); LLM — Llama offline. A
  full STT+diarization+LLM+TTS loop with no external calls.

**152-FZ / data-residency note (mandatory in design):** personal data of RU citizens — stored in RU.
Pattern: per-tenant `region=RU` → all calls/buckets/logs in RU DCs (Yandex ru-central1 or own DC);
**NO cross-region fallback** — under `region=RU` the offline fallback is ONLY local (Whisper+pyannote
+local LLM), not EU/US cloud. Separately: lawful consent to record/process speech, segregated
logs/analytics/embeddings in RU-only infra.

### Polyglot SDK (cross-lingual prod, no hard RU requirement)

- **Media/runtime:** LiveKit (SFU + LiveKit Agents) — WebRTC for user media, agent node reads tracks.
- **Brain:** OpenAI **Realtime** (speech-to-speech) over WebSocket from backend; turn_detection =
  `semantic_vad`, `create_response=true` + `interrupt_response=true` for barge-in.
- **Local turn-detection (extra control):** Pipecat **smart-turn-v2** or LiveKit turn-detector on PCM
  — semantic EOU, to not depend solely on the provider VAD.
- **TTS alternative:** ElevenLabs/own TTS if a different voice is needed — stream back into a LiveKit track.

## Risks / trade-offs

| Risk | Essence | Mitigation |
|:--|:--|:--|
| **WebSocket on media** | TCP head-of-line, +latency, stalls on packet loss | WebRTC/Opus on media; WebSocket ONLY on control |
| **VAD only** | cuts mid-sentence, false turn-ends on pauses/"uh…" | + semantic EOU; threshold on silence AND meaning |
| **Backchannel as takeover** | "uh-huh" mutes TTS, conversation breaks | word-count + semantics; not loudness alone |
| **Latency 1200 ms as target** | feels like IVR, not conversation | target < 800 ms, premium < 500; 1200 = legacy |
| **Blind backend** | no logs/PII-redaction/compliance | control channel through own node (sees every byte) |
| **Provider session limits** | e.g. SpeechKit ≤5 min/stream → drop on long call | rotate session in the machine without breaking talk |
| **Offline fallback on RU** | Whisper/RU-TTS weaker than cloud on telephony | lower expectations; premium quality — online cloud only |
| **Cross-region fallback under 152-FZ** | PD leaks outside RU on fallback | under region=RU fallback ONLY local, not EU/US |

## Hard prohibitions

FORBIDDEN:
- Running media over WebSocket for "simplicity" (latency/stalls) — media = WebRTC.
- Relying on one energy VAD for turn-taking.
- Muting TTS on any user sound (backchannel ≠ takeover).
- Taking 1200 ms as the target latency (that is the legacy-IVR bar).
- Under `region=RU`, falling back to EU/US STT/TTS/LLM — local offline only.
- Designing without an explicit session state-machine (barge-in will drift).

## Quality checklist

- [ ] Transport split: media = WebRTC, control/events = WebSocket (typed).
- [ ] Turn detection multi-layer: VAD + semantic EOU; threshold on silence AND completeness.
- [ ] Barge-in under 500 ms: instant TTS stop → listening; backchannel distinguished from takeover (word-count + semantics).
- [ ] Latency budget set with target under 800 ms (premium under 500); 1200 ms NOT used as target.
- [ ] Orchestration streams (partial STT → LLM tokens → TTS chunks), not full-final.
- [ ] Explicit session state-machine idle→listening→thinking→speaking with barge-in transition.
- [ ] Provider limits accounted for (e.g. SpeechKit ≤5 min/session — rotation).
- [ ] RU case: Yandex/Sber stack, offline fallback, 152-FZ note (region=RU, no cross-region fallback).

## Links

- OpenAI Realtime VAD/turn-detection: https://developers.openai.com/api/docs/guides/realtime-vad
- Pipecat smart-turn-v2 (semantic EOU, multilingual, RU): https://huggingface.co/pipecat-ai/smart-turn-v2
- Yandex SpeechKit STT (streaming gRPC v3): https://aistudio.yandex.ru/docs/en/speechkit/stt/
- Yandex AI Speech (voice-agent pipeline): https://aistudio.yandex.ru/en/ai-speech
- WhisperX + pyannote offline: https://github.com/m-bain/whisperX

## Related skills

- `architect/api-design` — WebSocket/gRPC control contract of the voice loop (events, function-calls).
- `architect/architecture` — broader context where the voice loop is one container of the system.
- `architect/security-design` — media-session auth, PII redaction on the control channel.
- `architect/legal-compliance` — 152-FZ / consent to record, data residency in detail.
