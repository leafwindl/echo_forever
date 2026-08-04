import 'dart:typed_data';

/// The phases used by the call screen.  `recording` and `recognizing` are
/// deliberately separate so a late partial result can never be mistaken for
/// a completed utterance.
enum CallPhase {
  connecting,
  ready,
  idle,
  recording,
  recognizing,
  thinking,
  speaking,
  userTurn,
  ended,
  error,
}

enum VoiceAudioFormat { pcm16le }

class CallState {
  const CallState({
    this.phase = CallPhase.connecting,
    this.partialText = '',
    this.userText = '',
    this.echoCaption = '',
    this.errorMessage,
    this.amplitude = 0,
    this.usingFallback = false,
    this.sessionGeneration = 0,
  });

  final CallPhase phase;
  final String partialText;
  final String userText;
  final String echoCaption;
  final String? errorMessage;
  final double amplitude;
  final bool usingFallback;
  final int sessionGeneration;

  bool get isActive => phase != CallPhase.ended;
  bool get isRecording => phase == CallPhase.recording;
  bool get isSpeaking => phase == CallPhase.speaking;
  bool get isBusy => switch (phase) {
    CallPhase.connecting ||
    CallPhase.recognizing ||
    CallPhase.thinking ||
    CallPhase.speaking => true,
    _ => false,
  };

  CallState copyWith({
    CallPhase? phase,
    String? partialText,
    String? userText,
    String? echoCaption,
    String? errorMessage,
    bool clearError = false,
    double? amplitude,
    bool? usingFallback,
    int? sessionGeneration,
  }) {
    return CallState(
      phase: phase ?? this.phase,
      partialText: partialText ?? this.partialText,
      userText: userText ?? this.userText,
      echoCaption: echoCaption ?? this.echoCaption,
      errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
      amplitude: amplitude ?? this.amplitude,
      usingFallback: usingFallback ?? this.usingFallback,
      sessionGeneration: sessionGeneration ?? this.sessionGeneration,
    );
  }
}

class VoiceStreamEvent {
  const VoiceStreamEvent.ready()
    : type = VoiceStreamEventType.ready,
      text = '',
      detail = '',
      closeCode = null;

  const VoiceStreamEvent.partial(this.text)
    : type = VoiceStreamEventType.partial,
      detail = '',
      closeCode = null;

  const VoiceStreamEvent.finalResult(this.text)
    : type = VoiceStreamEventType.finalResult,
      detail = '',
      closeCode = null;

  const VoiceStreamEvent.error(this.detail, {this.closeCode})
    : type = VoiceStreamEventType.error,
      text = '';

  const VoiceStreamEvent.closed(this.closeCode)
    : type = VoiceStreamEventType.closed,
      text = '',
      detail = '';

  final VoiceStreamEventType type;
  final String text;
  final String detail;
  final int? closeCode;
}

enum VoiceStreamEventType { ready, partial, finalResult, error, closed }

class RecordingResult {
  const RecordingResult({
    required this.path,
    required this.format,
    required this.bytes,
    required this.duration,
  });

  final String path;
  final VoiceAudioFormat format;
  final int bytes;
  final Duration duration;
}

/// Small value object used by fake recorders and by the PCM framer tests.
class PcmChunk {
  const PcmChunk(this.bytes);

  final Uint8List bytes;
}
