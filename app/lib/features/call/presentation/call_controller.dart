import 'dart:async';
import 'dart:collection';
import 'dart:io';
import 'dart:typed_data';

import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/call/data/call_chat_client.dart';
import 'package:echo_app/features/call/data/call_providers.dart';
import 'package:echo_app/features/call/data/temp_audio_store.dart';
import 'package:echo_app/features/call/data/web_socket_voice_client.dart';
import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:echo_app/features/call/domain/pcm_frame_assembler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

class CallController extends Notifier<CallState> {
  static const _readyBufferBytes = 64 * 1024;
  static const _readyBufferFrames = 10; // 2 seconds at 200 ms/frame.
  static const _sendHighWaterBytes = 5 * 6400; // 1 second.
  static const _sendCadence = Duration(milliseconds: 200);

  final PcmFrameAssembler _assembler = PcmFrameAssembler();
  final Queue<Uint8List> _readyFrames = Queue<Uint8List>();
  final Queue<Uint8List> _sendFrames = Queue<Uint8List>();
  StreamSubscription<Uint8List>? _chunkSubscription;
  StreamSubscription<double>? _amplitudeSubscription;
  StreamSubscription<VoiceStreamEvent>? _socketSubscription;
  StreamSubscription<bool>? _interruptionSubscription;
  Timer? _sendTimer;
  VoiceSocketSession? _socket;
  Future<void>? _socketOpening;
  RecordingResult? _recording;
  int _readyBytes = 0;
  int _sendBytes = 0;
  int _generation = 0;
  int _utterance = 0;
  int? _chatSentUtterance;
  bool _streamReady = false;
  bool _fallbackRequired = false;
  bool _terminalVoiceError = false;
  bool _streamingEnabled = false;
  bool _disposed = false;

  late RecorderAdapter _recorder;
  late VoiceSocketClient _socketClient;
  late VoiceUploadClient _upload;
  late CallChatClient _chat;
  late AudioPlayerAdapter _player;
  late AudioSessionAdapter _audioSession;
  late CallForegroundService _foreground;
  late TempAudioStore _tempStore;

  @override
  CallState build() {
    _disposed = false;
    _recorder = ref.read(recorderAdapterProvider);
    _socketClient = ref.read(voiceSocketClientProvider);
    _streamingEnabled = ref.read(voiceStreamingEnabledProvider);
    _upload = ref.read(voiceUploadClientProvider);
    _chat = ref.read(callChatClientProvider);
    _player = ref.read(audioPlayerAdapterProvider);
    _audioSession = ref.read(audioSessionAdapterProvider);
    _foreground = ref.read(callForegroundServiceProvider);
    _tempStore = ref.read(tempAudioStoreProvider);
    _interruptionSubscription = _audioSession.interruptionStream.listen((
      begin,
    ) {
      if (begin) unawaited(handleAudioInterruption());
    });
    ref.onDispose(() {
      _disposed = true;
      unawaited(_interruptionSubscription?.cancel());
      unawaited(_endResources(cancelRecorder: true));
    });
    return const CallState();
  }

  Future<void> connect() async {
    if (state.phase != CallPhase.connecting && state.phase != CallPhase.ended) {
      return;
    }
    final generation = ++_generation;
    state = CallState(
      phase: CallPhase.connecting,
      sessionGeneration: generation,
    );
    try {
      await _audioSession.configure();
      await _foreground.start(onStopRequested: hangUp);
      if (!_isCurrent(generation)) return;
      state = state.copyWith(phase: CallPhase.ready, clearError: true);
      await Future<void>.delayed(Duration.zero);
      if (_isCurrent(generation) && state.phase == CallPhase.ready) {
        state = state.copyWith(phase: CallPhase.idle);
      }
    } on Object {
      if (!_isCurrent(generation)) return;
      state = state.copyWith(
        phase: CallPhase.error,
        errorMessage: '无法建立通话，请稍后重试。',
      );
    }
  }

  Future<bool> startRecording() async {
    final allowed = switch (state.phase) {
      CallPhase.idle ||
      CallPhase.ready ||
      CallPhase.userTurn ||
      CallPhase.speaking => true,
      _ => false,
    };
    if (!allowed || _disposed) return false;
    final generation = _generation;
    final utterance = ++_utterance;
    _chatSentUtterance = null;
    if (state.phase == CallPhase.speaking) {
      state = state.copyWith(phase: CallPhase.userTurn);
      await _player.stop();
    }
    try {
      final permitted = await _recorder.requestPermission();
      if (!permitted) {
        if (_isUtteranceCurrent(generation, utterance)) {
          state = state.copyWith(
            phase: CallPhase.idle,
            errorMessage: '需要麦克风权限才能和 Echo 通话。',
          );
        }
        return false;
      }
      await _player.stop();
      await _audioSession.beginRecording();
      if (!_isUtteranceCurrent(generation, utterance)) return false;
      _resetStreamingState();
      _chunkSubscription = _recorder.chunks.listen(
        (chunk) => _onPcmChunk(chunk, generation, utterance),
        onError: (Object _) =>
            unawaited(cancelRecording(message: '没录到声音，请重试。')),
      );
      _amplitudeSubscription = _recorder.amplitude.listen((value) {
        if (_isUtteranceCurrent(generation, utterance) &&
            state.phase == CallPhase.recording) {
          state = state.copyWith(amplitude: value);
        }
      });
      await _recorder.start();
      if (!_isUtteranceCurrent(generation, utterance)) return false;
      state = state.copyWith(
        phase: CallPhase.recording,
        partialText: '',
        userText: '',
        echoCaption: '',
        amplitude: 0,
        usingFallback: false,
        clearError: true,
      );
      if (_streamingEnabled) {
        _beginSocketOpen(generation, utterance);
      }
      return true;
    } on Object {
      if (_isUtteranceCurrent(generation, utterance)) {
        await _recorder.cancel();
        state = state.copyWith(
          phase: CallPhase.idle,
          errorMessage: '录音启动失败，请重试。',
        );
      }
      return false;
    }
  }

  void _beginSocketOpen(int generation, int utterance) {
    final opening = _openSocket(generation, utterance);
    _socketOpening = opening;
    unawaited(
      opening.whenComplete(() {
        if (identical(_socketOpening, opening)) _socketOpening = null;
      }),
    );
  }

  Future<void> _openSocket(int generation, int utterance) async {
    try {
      final socket = await _socketClient.open(requestId: const Uuid().v4());
      if (!_isUtteranceCurrent(generation, utterance) ||
          (state.phase != CallPhase.recording &&
              state.phase != CallPhase.recognizing)) {
        await socket.cancel();
        return;
      }
      _socket = socket;
      _socketSubscription = socket.events.listen(
        (event) => _onSocketEvent(event, generation, utterance),
        onError: (Object _) => _requireFallback('socket_error'),
      );
      await socket.ready;
      if (_isUtteranceCurrent(generation, utterance) &&
          !_fallbackRequired &&
          !_streamReady) {
        _onSocketEvent(const VoiceStreamEvent.ready(), generation, utterance);
      }
    } on Object {
      if (_isUtteranceCurrent(generation, utterance)) {
        _requireFallback('ready_failed');
      }
    }
  }

  void _onSocketEvent(VoiceStreamEvent event, int generation, int utterance) {
    if (!_isUtteranceCurrent(generation, utterance)) return;
    switch (event.type) {
      case VoiceStreamEventType.ready:
        _streamReady = true;
        while (_readyFrames.isNotEmpty && !_fallbackRequired) {
          final frame = _readyFrames.removeFirst();
          _readyBytes -= frame.length;
          _enqueueSend(frame);
        }
        _startSendDrain();
      case VoiceStreamEventType.partial:
        if (state.phase == CallPhase.recording ||
            state.phase == CallPhase.recognizing) {
          state = state.copyWith(partialText: event.text);
        }
      case VoiceStreamEventType.finalResult:
        if (event.text.isNotEmpty) {
          state = state.copyWith(partialText: event.text);
        }
      case VoiceStreamEventType.error:
        if (_shouldNotFallback(event.closeCode)) {
          _terminalVoiceError = true;
          state = state.copyWith(
            errorMessage: _closeCodeMessage(event.closeCode),
          );
        } else {
          _requireFallback('server_error');
        }
      case VoiceStreamEventType.closed:
        if (_shouldNotFallback(event.closeCode)) {
          _terminalVoiceError = true;
          state = state.copyWith(
            errorMessage: _closeCodeMessage(event.closeCode),
          );
        } else if ((state.phase == CallPhase.recording ||
                state.phase == CallPhase.recognizing) &&
            !_streamReady) {
          _requireFallback('closed_before_ready');
        }
    }
  }

  void _onPcmChunk(Uint8List chunk, int generation, int utterance) {
    if (!_isUtteranceCurrent(generation, utterance) ||
        (state.phase != CallPhase.recording &&
            state.phase != CallPhase.recognizing)) {
      return;
    }
    if (!_streamingEnabled) return;
    for (final frame in _assembler.add(chunk)) {
      _handleFrame(frame);
    }
  }

  void _handleFrame(Uint8List frame) {
    if (_fallbackRequired || _terminalVoiceError) return;
    if (!_streamReady || _socket == null) {
      if (_readyFrames.length >= _readyBufferFrames ||
          _readyBytes + frame.length > _readyBufferBytes) {
        _requireFallback('ready_buffer_overflow');
        return;
      }
      _readyFrames.add(frame);
      _readyBytes += frame.length;
      return;
    }
    _enqueueSend(frame);
    _startSendDrain();
  }

  void _enqueueSend(Uint8List frame) {
    if (_sendBytes + frame.length > _sendHighWaterBytes) {
      _requireFallback('send_backpressure');
      return;
    }
    _sendFrames.add(frame);
    _sendBytes += frame.length;
  }

  void _startSendDrain() {
    if (_fallbackRequired || _sendTimer != null) return;
    _drainOneFrame();
    if (_sendFrames.isNotEmpty) {
      _sendTimer = Timer.periodic(_sendCadence, (_) => _drainOneFrame());
    }
  }

  void _drainOneFrame() {
    if (_fallbackRequired || _sendFrames.isEmpty) {
      _sendTimer?.cancel();
      _sendTimer = null;
      return;
    }
    final frame = _sendFrames.removeFirst();
    _sendBytes -= frame.length;
    if (!(_socket?.sendAudio(frame) ?? false)) {
      _requireFallback('socket_backpressure');
    }
  }

  Future<bool> stopRecording() async {
    if (state.phase != CallPhase.recording || _disposed) return false;
    final generation = _generation;
    final utterance = _utterance;
    var resourcesFinished = false;
    state = state.copyWith(
      phase: CallPhase.recognizing,
      amplitude: 0,
      clearError: true,
    );
    try {
      _recording = await _recorder.stop();
      await Future<void>.delayed(Duration.zero);
      await _chunkSubscription?.cancel();
      await _amplitudeSubscription?.cancel();
      _chunkSubscription = null;
      _amplitudeSubscription = null;
      for (final tail in _assembler.flush()) {
        _handleFrame(tail);
      }
      final socketOpening = _socketOpening;
      if (socketOpening != null) await socketOpening;
      if (!_isUtteranceCurrent(generation, utterance)) return false;
      String text;
      if (_terminalVoiceError) {
        throw StateError(state.errorMessage ?? '语音请求不可用');
      }
      if (_fallbackRequired || _socket == null || !_streamReady) {
        text = await _recognizeFallback(generation, utterance);
      } else {
        await _waitForSendDrain(generation, utterance);
        if (_fallbackRequired) {
          text = await _recognizeFallback(generation, utterance);
        } else {
          try {
            text = (await _socket!.finish()).trim();
          } on Object catch (error) {
            if (_shouldNotFallback(_closeCode(error))) rethrow;
            text = await _recognizeFallback(generation, utterance);
          }
          if (text.isEmpty) {
            text = await _recognizeFallback(generation, utterance);
          }
        }
      }
      if (!_isUtteranceCurrent(generation, utterance)) return false;
      if (text.trim().isEmpty) throw StateError('没有识别到内容');
      await _finishUtteranceResources();
      resourcesFinished = true;
      return await _requestReply(text.trim(), generation, utterance);
    } on Object catch (error) {
      if (_isUtteranceCurrent(generation, utterance)) {
        state = state.copyWith(
          phase: CallPhase.idle,
          errorMessage: _voiceErrorMessage(error),
        );
      }
      return false;
    } finally {
      if (!resourcesFinished) await _finishUtteranceResources();
    }
  }

  Future<String> _recognizeFallback(int generation, int utterance) async {
    if (!_isUtteranceCurrent(generation, utterance) || _recording == null) {
      return '';
    }
    state = state.copyWith(usingFallback: true);
    return (await _upload.recognize(_recording!)).trim();
  }

  Future<bool> _requestReply(String text, int generation, int utterance) async {
    if (_chatSentUtterance == utterance) return false;
    _chatSentUtterance = utterance;
    state = state.copyWith(
      phase: CallPhase.thinking,
      userText: text,
      partialText: '',
      clearError: true,
    );
    final CallChatReply reply = await _chat.send(text);
    if (!_isUtteranceCurrent(generation, utterance)) return false;
    state = state.copyWith(echoCaption: reply.reply.trim());
    if (reply.audioUrls.isEmpty) {
      state = state.copyWith(
        phase: CallPhase.idle,
        errorMessage: '回复已显示，语音暂时不可用。',
      );
      return true;
    }
    state = state.copyWith(phase: CallPhase.speaking);
    await _audioSession.beginPlayback();
    try {
      await _player.playSegments(
        reply.audioUrls,
        shouldContinue: () =>
            _isUtteranceCurrent(generation, utterance) &&
            state.phase == CallPhase.speaking,
      );
    } on Object {
      if (_isUtteranceCurrent(generation, utterance)) {
        state = state.copyWith(errorMessage: '回复已显示，音频播放中断。');
      }
    }
    if (_isUtteranceCurrent(generation, utterance) &&
        state.phase == CallPhase.speaking) {
      state = state.copyWith(phase: CallPhase.idle);
    }
    return true;
  }

  Future<void> _waitForSendDrain(int generation, int utterance) async {
    final deadline = DateTime.now().add(const Duration(seconds: 15));
    while (_sendFrames.isNotEmpty &&
        _isUtteranceCurrent(generation, utterance) &&
        DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    if (_sendFrames.isNotEmpty) _requireFallback('send_drain_timeout');
  }

  Future<void> cancelRecording({String? message}) async {
    if (state.phase != CallPhase.recording &&
        state.phase != CallPhase.recognizing) {
      return;
    }
    _utterance += 1;
    await _recorder.cancel();
    await _finishUtteranceResources();
    if (!_disposed && state.phase != CallPhase.ended) {
      state = state.copyWith(
        phase: CallPhase.idle,
        partialText: '',
        amplitude: 0,
        errorMessage: message,
        clearError: message == null,
      );
    }
  }

  Future<void> handleAudioInterruption() async {
    switch (state.phase) {
      case CallPhase.recording || CallPhase.recognizing:
        await cancelRecording(message: '录音被系统音频中断，请重新说一次。');
      case CallPhase.speaking:
        _utterance += 1;
        await _player.stop();
        if (!_disposed) {
          state = state.copyWith(
            phase: CallPhase.idle,
            errorMessage: '播放被系统音频中断。',
          );
        }
      default:
        break;
    }
  }

  Future<void> hangUp() async {
    if (state.phase == CallPhase.ended) return;
    _generation += 1;
    _utterance += 1;
    state = state.copyWith(
      phase: CallPhase.ended,
      partialText: '',
      amplitude: 0,
      sessionGeneration: _generation,
    );
    await _endResources(cancelRecorder: true);
  }

  void clearError() => state = state.copyWith(clearError: true);

  void _requireFallback(String _) {
    if (_terminalVoiceError || _fallbackRequired) return;
    _fallbackRequired = true;
    _sendTimer?.cancel();
    _sendTimer = null;
    _readyFrames.clear();
    _sendFrames.clear();
    _readyBytes = 0;
    _sendBytes = 0;
    final socket = _socket;
    if (socket != null) unawaited(socket.cancel());
  }

  Future<void> _finishUtteranceResources() async {
    _sendTimer?.cancel();
    _sendTimer = null;
    await _chunkSubscription?.cancel();
    await _amplitudeSubscription?.cancel();
    await _socketSubscription?.cancel();
    _chunkSubscription = null;
    _amplitudeSubscription = null;
    _socketSubscription = null;
    final socket = _socket;
    _socket = null;
    _socketOpening = null;
    if (socket != null) await socket.close();
    final recording = _recording;
    _recording = null;
    if (recording != null) {
      try {
        await _tempStore.delete(recording.path);
      } on FileSystemException {
        // Best effort cache cleanup; startup orphan cleanup is the safety net.
      }
    }
    _resetStreamingState();
  }

  Future<void> _endResources({required bool cancelRecorder}) async {
    if (cancelRecorder) {
      try {
        await _recorder.cancel();
      } on Object {
        // Resource cleanup must continue even when a plugin is already gone.
      }
    }
    await _finishUtteranceResources();
    await _player.stop();
    await _foreground.stopService();
    await _audioSession.release();
  }

  void _resetStreamingState() {
    _assembler.clear();
    _readyFrames.clear();
    _sendFrames.clear();
    _readyBytes = 0;
    _sendBytes = 0;
    _streamReady = false;
    _fallbackRequired = false;
    _terminalVoiceError = false;
  }

  bool _isCurrent(int generation) => !_disposed && generation == _generation;

  bool _isUtteranceCurrent(int generation, int utterance) =>
      _isCurrent(generation) && utterance == _utterance;

  static bool _shouldNotFallback(int? code) => code == 1009 || code == 4429;

  static int? _closeCode(Object error) =>
      error is VoiceStreamClosedException ? error.closeCode : null;

  static String _closeCodeMessage(int? code) => switch (code) {
    1009 => '录音过长，请缩短后重试。',
    4429 => '语音请求过于频繁，请稍后再试。',
    _ => '语音识别失败，请重试。',
  };

  static String _voiceErrorMessage(Object error) {
    if (error is AppException) {
      return switch (error.kind) {
        AppExceptionKind.rateLimited => '语音请求过于频繁，请稍后再试。',
        AppExceptionKind.payloadTooLarge => '录音过长，请缩短后重试。',
        AppExceptionKind.unauthorized => '登录状态已失效，请重新登录。',
        _ => error.detail ?? '刚刚没听清，请再说一次。',
      };
    }
    return '刚刚没听清，请再说一次。';
  }
}

final callControllerProvider =
    NotifierProvider.autoDispose<CallController, CallState>(CallController.new);
