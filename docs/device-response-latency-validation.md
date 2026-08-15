# Device Response Latency Validation

Date: 2026-08-15

This report records the backend validation for the three-stage latency plan. The
device firmware protocol remains unchanged in this iteration. Measurements below
were collected on 2026-08-15 from the deployed server at `/opt/echo/app`.

## Implementation Status

- Stage 1: completed in the backend. The device uses a call-mode reply constraint,
  650 ms VAD, and a 30 s maximum automatic capture window.
- Stage 2: completed in the backend. DeepSeek text, natural clauses, CosyVoice
  PCM16, incremental Opus encoding, and device WebSocket delivery overlap.
- Stage 3: backend path enabled for validation. Tencent streaming ASR receives
  decoded 16 kHz PCM during capture; failed or empty streaming results fall back
  to batch ASR. Long-connection, barge-in, and AEC work remains pending.

## Automated Verification

- Full backend test suite: `364 passed`
- Python bytecode compilation: passed
- Architecture check, Ruff, and Git whitespace check: passed

## Provider Measurements

The following measurements were made locally with the configured providers.

| Component | Input | Result |
| --- | --- | ---: |
| DeepSeek stream | short Chinese prompt, thinking disabled | first text delta about 0.5–0.9 s in repeated server samples |
| CosyVoice PCM stream | short Chinese clause | first PCM chunk about 0.67–0.75 s |
| PCM to Opus | same CosyVoice stream | 32 packets, no encoder error |

The DeepSeek request uses the same model configured for APP chat. No second LLM
was introduced for the device.

## Long-ASR Baseline

These runs used generated Mandarin speech converted to 16 kHz mono PCM. They
measure Tencent batch ASR only; they are not a substitute for a real hardware
microphone test.

| Audio duration | ASR time | Realtime factor |
| ---: | ---: | ---: |
| 5.62 s | 980 ms | 0.175 |
| 15.50 s | 818 ms | 0.053 |
| 29.81 s | 721 ms | 0.024 |

The result confirms that the earlier 143 ms observation was a short-utterance
sample, not a fixed delay. The device logs now include audio duration,
recognition duration, and realtime factor for real microphone runs.

## Concurrent Device Probe

The probe sends 60 ms Opus packets and receives server messages concurrently.
It is not a substitute for speaking into Bread Compact, but it removes the
measurement error where all trailing silence was sent before receiving began.

With streaming replies enabled and batch ASR, five short synthetic turns gave:

| Metric | P50 | Range |
| --- | ---: | ---: |
| Speech end to ASR text | 730 ms | 700–732 ms |
| Speech end to first TTS event | 1,821 ms | 1,562–1,973 ms |
| Speech end to first device audio | 2,544 ms | 2,259–2,667 ms |

The same path with Tencent realtime ASR produced a first device audio sample of
about 2.43 s. The original Stage 2 target of 1.6 s is not met with the current
cloud providers: the 650 ms VAD and approximately 0.7 s CosyVoice first packet
already consume about 1.35 s before context and model time. Reaching 1.6 s would
require a materially faster/local TTS path or a separate immediate acknowledgement
audio, not another tuning pass on the same pipeline.

## Realtime ASR Boundary Probe

These are generated PCM inputs, not real microphone accuracy tests. They verify
capture duration, finalization, and the 30 s boundary:

| Input speech | Server captured | Final text | First device audio |
| ---: | ---: | ---: | ---: |
| 5 s | 5.70 s | returned | 2.65 s |
| 15 s | 15.72 s | returned | 2.42 s |
| 30 s | 30.36 s | returned | 2.45 s |

The repeated probe phrase is intentionally not used to judge ASR wording. A
real-device pass is still required for microphone noise, pauses, and accuracy.

## Runtime Flags

All new behavior is reversible without a firmware reflash:

```dotenv
ECHO_DEVICE_AUTO_SILENCE_MS=650
ECHO_DEVICE_AUTO_MAXIMUM_SPEECH_MS=30000
ECHO_DEVICE_STREAMING_ENABLED=true
ECHO_DEVICE_REALTIME_ASR_ENABLED=true
ECHO_DEVICE_TOOLS_ENABLED=false
VOICE_STREAMING_ASR_ENABLED=true
ECHO_DEVICE_TTS_CHUNK_MAX_CHARS=18
```

Device tools are disabled by default only for the low-latency streaming device
path. APP chat keeps the existing Agent tool configuration. When device tools
are enabled, the final reply fallback still guarantees that TTS is not silent.

The deployed server currently uses the enabled values above. To roll back without
flashing the device, set `ECHO_DEVICE_STREAMING_ENABLED=false` and
`ECHO_DEVICE_REALTIME_ASR_ENABLED=false`, then recreate `echo-backend`.

## Remaining Hardware Acceptance

1. On Bread Compact, run 20 short half-duplex turns and record
   `speech_end_to_device_first_audio_ms` from the server log.
2. Confirm the APP receives exactly one complete user/reply turn per test and
   that playback has no audible gaps.
3. Repeat with real 5 s, 15 s, and 30 s utterances; check natural pauses are not
   cut and that realtime ASR falls back to batch when disabled or unavailable.
4. Test a Wi-Fi interruption and confirm the current firmware reconnects; the
   planned persistent WebSocket and playback interruption are not yet accepted.
