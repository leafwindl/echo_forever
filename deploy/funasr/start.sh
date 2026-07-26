#!/usr/bin/env bash
set -euo pipefail

cd /workspace/FunASR/runtime

decoder_threads="${FUNASR_DECODER_THREADS:-$(nproc)}"
io_threads=$(( (decoder_threads + 15) / 16 ))

server_args=(
  --download-model-dir "${FUNASR_MODEL_DIR}"
  --model-dir "${FUNASR_OFFLINE_MODEL}"
  --online-model-dir "${FUNASR_ONLINE_MODEL}"
  --vad-dir "${FUNASR_VAD_MODEL}"
  --punc-dir "${FUNASR_PUNC_MODEL}"
  --itn-dir "${FUNASR_ITN_MODEL}"
  --lm-dir "${FUNASR_LM_MODEL:-}"
  --decoder-thread-num "${decoder_threads}"
  --model-thread-num 1
  --io-thread-num "${io_threads}"
  --port 10095
  --certfile ""
  --keyfile ""
)

exec /workspace/FunASR/runtime/websocket/build/bin/funasr-wss-server-2pass "${server_args[@]}"
