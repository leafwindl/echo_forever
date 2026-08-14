# Devices Feature

Devices is the hardware access boundary for the Echo desk companion. It accepts
Xiaozhi-compatible WebSocket protocol v1 and raw Opus packets, then reuses the
existing Voice and Chat features for ASR, persona/memory-aware replies, TTS, and
chat persistence.

## First-stage flow

```text
ESP32 hello/listen/Opus
  -> decode 16 kHz PCM16LE
  -> existing ASR provider
  -> existing synchronous call chat flow
  -> existing TTS provider
  -> encode 24 kHz / 60 ms Opus packets
  -> ESP32 playback
```

The synchronous call flow stores `voice_asr` and `voice_reply` messages in the
normal user conversation. Devices publishes a `chat.sync` event after the turn
so an open app can merge the same messages immediately.

## Personal-device authentication

Stage one intentionally supports a single private deployment through:

```dotenv
ECHO_DEVICE_TOKEN=<random secret>
ECHO_DEVICE_USER_MAP_JSON={"aa:bb:cc:dd:ee:ff|device-client-uuid":"echo-user-id"}
```

A full-image flash can create a new `Client-Id`. For the first Echo boot, a
device-scoped wildcard may be used temporarily:

```dotenv
ECHO_DEVICE_USER_MAP_JSON={"aa:bb:cc:dd:ee:ff|*":"echo-user-id"}
```

After reading the new `Client-Id` from the serial log, replace `*` with that
exact value. Exact mappings take precedence over the wildcard.

The device token is separate from the app access token. The bootstrap endpoint
requires a configured device mapping before returning the WebSocket
configuration.
This is a personal prototype boundary; formal app pairing will replace the
environment mapping with revocable database-backed device credentials.

## Supported protocol

- WebSocket protocol version 1 only.
- Uplink: Opus, 16 kHz mono, 60 ms frames.
- Downlink: Opus, 24 kHz mono, 60 ms frames.
- Half-duplex one-utterance turns.
- `hello`, `listen.start`, `listen.stop`, `abort`, `stt`, and `tts` messages.

Protocol v2/v3, realtime ASR, full-duplex AEC, MCP tools, cameras, and motion are
outside the first-stage contract.
