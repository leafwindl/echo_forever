# Device Response Latency Validation

Date: 2026-08-15

This report records the backend validation for the three-stage latency plan. The
device firmware protocol remains unchanged in this iteration.

## Implementation Status

- Stage 1: completed. Short call replies are constrained by the call prompt and
  the device VAD default is configurable through `.env`.
- Stage 2: completed in a feature-flagged path. The existing DeepSeek model can
  stream text, completed sentences are sent to CosyVoice, PCM16 is encoded to
  24 kHz mono Opus packets, and packets are sent over the existing device
  WebSocket.
- Stage 3: backend support completed in a feature-flagged path. The device's
  decoded 16 kHz PCM can be uploaded to Tencent streaming ASR while capture is
  in progress. A failed or empty streaming result falls back to batch ASR.

## Automated Verification

- Device, agent, provider, and voice tests: `90 passed`
- Python bytecode compilation: passed
- Git whitespace check: passed

## Provider Measurements

The following measurements were made locally with the configured providers.

| Component | Input | Result |
| --- | --- | ---: |
| DeepSeek stream | short Chinese prompt, thinking disabled | first text delta about 777 ms; complete response about 1,058 ms |
| CosyVoice PCM stream | `\u6211\u5728\u5462\uff0c\u8bf7\u8bf4\u3002` | first PCM chunk about 795 ms; complete stream about 996 ms |
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

## Runtime Flags

All new behavior is reversible without a firmware reflash:

```dotenv
ECHO_DEVICE_STREAMING_ENABLED=false
ECHO_DEVICE_REALTIME_ASR_ENABLED=false
ECHO_DEVICE_TOOLS_ENABLED=false
VOICE_STREAMING_ASR_ENABLED=false
```

Device tools are disabled by default only for the low-latency streaming device
path. APP chat keeps the existing Agent tool configuration. When device tools
are enabled, the final reply fallback still guarantees that TTS is not silent.

Enable Stage 2 only after the existing batch path passes a hardware smoke test.
Enable Stage 3 only when Tencent streaming credentials and the real device
capture path have been verified.

## Remaining Hardware Acceptance

1. Enable Stage 2 on the server and run at least 20 short half-duplex turns.
2. Record `speech_end_to_device_first_audio_ms` and verify the P50 target of
   1.6 seconds for the first natural sentence.
3. Enable Stage 3 and repeat with 5 s, 15 s, and 30 s real utterances.
4. Verify APP persistence, reconnect, and batch-ASR fallback before enabling
   the feature flags by default.
