from typing import Optional

from features.voice.application.use_cases import RecognizeVoice, SynthesizeVoiceReply
from features.voice.infrastructure.adapters import (
    EdgeVoiceSynthesizer,
    LocalVoiceAudioStorage,
    TencentVoiceRecognizer,
)

_recognize_voice_use_case: Optional[RecognizeVoice] = None
_synthesize_voice_reply_use_case: Optional[SynthesizeVoiceReply] = None


def get_recognize_voice_use_case() -> RecognizeVoice:
    global _recognize_voice_use_case
    if _recognize_voice_use_case is None:
        _recognize_voice_use_case = RecognizeVoice(
            audio_storage=LocalVoiceAudioStorage(),
            recognizer=TencentVoiceRecognizer(),
        )
    return _recognize_voice_use_case


def get_synthesize_voice_reply_use_case() -> SynthesizeVoiceReply:
    global _synthesize_voice_reply_use_case
    if _synthesize_voice_reply_use_case is None:
        _synthesize_voice_reply_use_case = SynthesizeVoiceReply(
            synthesizer=EdgeVoiceSynthesizer(),
            audio_storage=LocalVoiceAudioStorage(),
        )
    return _synthesize_voice_reply_use_case


def reset_voice_use_cases_for_tests():
    global _recognize_voice_use_case, _synthesize_voice_reply_use_case
    _recognize_voice_use_case = None
    _synthesize_voice_reply_use_case = None
