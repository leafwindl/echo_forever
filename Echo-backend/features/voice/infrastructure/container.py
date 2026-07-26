from shared.config import settings

from features.voice.application.use_cases import (
    OpenStreamingVoiceRecognition,
    RecognizeVoice,
    SynthesizeVoiceReply,
)
from features.voice.infrastructure.adapters import (
    LocalVoiceAudioStorage,
    ProviderVoiceSynthesizer,
    TencentVoiceRecognizer,
)
from features.voice.infrastructure.streaming_asr import FunASRStreamingVoiceRecognizer

_recognize_voice_use_case: RecognizeVoice | None = None
_synthesize_voice_reply_use_case: SynthesizeVoiceReply | None = None
_open_streaming_voice_recognition_use_case: OpenStreamingVoiceRecognition | None = None


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
            synthesizer=ProviderVoiceSynthesizer(),
            audio_storage=LocalVoiceAudioStorage(),
            segment_max_chars=settings.tts_segment_max_chars,
            reply_max_chars=settings.tts_reply_max_chars,
        )
    return _synthesize_voice_reply_use_case


def get_open_streaming_voice_recognition_use_case() -> OpenStreamingVoiceRecognition:
    global _open_streaming_voice_recognition_use_case
    if _open_streaming_voice_recognition_use_case is None:
        _open_streaming_voice_recognition_use_case = OpenStreamingVoiceRecognition(
            recognizer=FunASRStreamingVoiceRecognizer()
        )
    return _open_streaming_voice_recognition_use_case


def reset_voice_use_cases_for_tests():
    global _recognize_voice_use_case, _synthesize_voice_reply_use_case
    global _open_streaming_voice_recognition_use_case
    _recognize_voice_use_case = None
    _synthesize_voice_reply_use_case = None
    _open_streaming_voice_recognition_use_case = None
