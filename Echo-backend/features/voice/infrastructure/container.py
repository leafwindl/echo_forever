from typing import Optional

from features.voice.application.use_cases import GenerateVoiceReply, RecognizeVoice
from features.voice.infrastructure.adapters import (
    ChatVoiceResponder,
    EdgeVoiceSynthesizer,
    LocalVoiceAudioStorage,
    TencentVoiceRecognizer,
)

_recognize_voice_use_case: Optional[RecognizeVoice] = None
_generate_voice_reply_use_case: Optional[GenerateVoiceReply] = None


def get_recognize_voice_use_case() -> RecognizeVoice:
    global _recognize_voice_use_case
    if _recognize_voice_use_case is None:
        _recognize_voice_use_case = RecognizeVoice(
            audio_storage=LocalVoiceAudioStorage(),
            recognizer=TencentVoiceRecognizer(),
        )
    return _recognize_voice_use_case


def get_generate_voice_reply_use_case() -> GenerateVoiceReply:
    global _generate_voice_reply_use_case
    if _generate_voice_reply_use_case is None:
        _generate_voice_reply_use_case = GenerateVoiceReply(
            chat_responder=ChatVoiceResponder(),
            synthesizer=EdgeVoiceSynthesizer(),
            audio_storage=LocalVoiceAudioStorage(),
        )
    return _generate_voice_reply_use_case


def reset_voice_use_cases_for_tests():
    global _recognize_voice_use_case, _generate_voice_reply_use_case
    _recognize_voice_use_case = None
    _generate_voice_reply_use_case = None
