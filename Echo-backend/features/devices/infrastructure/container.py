from features.devices.application.process_voice_turn import ProcessDeviceVoiceTurn
from features.devices.infrastructure.adapters import (
    EchoChatNotifier,
    EchoConversationService,
    EchoVoiceRecognizer,
)

_process_device_voice_turn: ProcessDeviceVoiceTurn | None = None


def get_process_device_voice_turn() -> ProcessDeviceVoiceTurn:
    global _process_device_voice_turn
    if _process_device_voice_turn is None:
        _process_device_voice_turn = ProcessDeviceVoiceTurn(
            recognizer=EchoVoiceRecognizer(),
            conversation=EchoConversationService(),
            notifier=EchoChatNotifier(),
        )
    return _process_device_voice_turn


def reset_device_services_for_tests() -> None:
    global _process_device_voice_turn
    _process_device_voice_turn = None
