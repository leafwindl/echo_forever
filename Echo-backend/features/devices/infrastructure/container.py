from features.devices.application.process_voice_turn import ProcessDeviceVoiceTurn
from features.devices.application.stream_voice_turn import StreamDeviceVoiceTurn
from features.devices.infrastructure.adapters import (
    EchoChatNotifier,
    EchoConversationService,
    EchoSpeechSynthesizer,
    EchoVoiceRecognizer,
)

_process_device_voice_turn: ProcessDeviceVoiceTurn | None = None
_stream_device_voice_turn: StreamDeviceVoiceTurn | None = None


def get_process_device_voice_turn() -> ProcessDeviceVoiceTurn:
    global _process_device_voice_turn
    if _process_device_voice_turn is None:
        _process_device_voice_turn = ProcessDeviceVoiceTurn(
            recognizer=EchoVoiceRecognizer(),
            conversation=EchoConversationService(),
            notifier=EchoChatNotifier(),
        )
    return _process_device_voice_turn


def get_stream_device_voice_turn() -> StreamDeviceVoiceTurn:
    global _stream_device_voice_turn
    if _stream_device_voice_turn is None:
        from shared.config import settings

        _stream_device_voice_turn = StreamDeviceVoiceTurn(
            recognizer=EchoVoiceRecognizer(),
            conversation=EchoConversationService(),
            speech=EchoSpeechSynthesizer(),
            notifier=EchoChatNotifier(),
            chunk_max_chars=settings.echo_device_tts_chunk_max_chars,
            chunk_min_chars=settings.echo_device_tts_chunk_min_chars,
            queue_max_packets=settings.echo_device_audio_queue_max_packets,
            prefetch_phrases=settings.echo_device_tts_prefetch_phrases,
            maximum_silence_ms=settings.echo_device_tts_max_silence_ms,
            silence_rms_threshold=settings.echo_device_tts_silence_rms_threshold,
        )
    return _stream_device_voice_turn


def reset_device_services_for_tests() -> None:
    global _process_device_voice_turn, _stream_device_voice_turn
    _process_device_voice_turn = None
    _stream_device_voice_turn = None
