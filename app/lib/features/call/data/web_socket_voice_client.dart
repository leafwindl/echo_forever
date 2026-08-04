import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as status;

class WebSocketVoiceClient implements VoiceSocketClient {
  WebSocketVoiceClient({required this.baseUrl, required this.accessToken});

  final String baseUrl;
  final String accessToken;

  @override
  Future<VoiceSocketSession> open({required String requestId}) async {
    final uri = Uri.parse(baseUrl).replace(
      scheme: Uri.parse(baseUrl).scheme == 'https' ? 'wss' : 'ws',
      path: '/voice/asr/stream',
    );
    final channel = IOWebSocketChannel.connect(
      uri,
      headers: <String, String>{
        'Authorization': 'Bearer $accessToken',
        'X-Request-ID': requestId,
      },
      connectTimeout: const Duration(seconds: 5),
    );
    return _WebSocketVoiceSession(channel);
  }
}

class _WebSocketVoiceSession implements VoiceSocketSession {
  _WebSocketVoiceSession(this._channel) {
    _listen();
    _readyTimer = Timer(const Duration(seconds: 5), () {
      if (!_ready.isCompleted) {
        _fail(StateError('流式语音服务连接超时'));
        unawaited(close());
      }
    });
  }

  final IOWebSocketChannel _channel;
  final StreamController<VoiceStreamEvent> _events =
      StreamController<VoiceStreamEvent>.broadcast();
  final Completer<void> _ready = Completer<void>();
  final Completer<String> _final = Completer<String>();
  Timer? _readyTimer;
  Timer? _finalTimer;
  bool _closed = false;
  bool _finishRequested = false;
  int? _closeCode;

  @override
  Stream<VoiceStreamEvent> get events => _events.stream;

  void _listen() {
    _channel.stream.listen(
      (message) {
        if (message is! String) return;
        Map<String, dynamic> json;
        try {
          json = jsonDecode(message) as Map<String, dynamic>;
        } catch (_) {
          return;
        }
        switch (json['type']) {
          case 'ready':
            if (!_ready.isCompleted) {
              _readyTimer?.cancel();
              _ready.complete();
            }
            _events.add(const VoiceStreamEvent.ready());
          case 'partial':
            _events.add(
              VoiceStreamEvent.partial((json['text'] as String? ?? '').trim()),
            );
          case 'final':
            final text = (json['text'] as String? ?? '').trim();
            _events.add(VoiceStreamEvent.finalResult(text));
            if (!_final.isCompleted) _final.complete(text);
            _finalTimer?.cancel();
          case 'error':
            final detail = json['detail'] as String? ?? '流式语音识别失败';
            _events.add(VoiceStreamEvent.error(detail, closeCode: _closeCode));
            if (!_final.isCompleted) _final.completeError(StateError(detail));
        }
      },
      onError: (Object error, StackTrace stack) {
        _events.add(VoiceStreamEvent.error(error.toString()));
        _fail(error, stack);
      },
      onDone: () {
        _closed = true;
        _readyTimer?.cancel();
        _finalTimer?.cancel();
        _events.add(VoiceStreamEvent.closed(_channel.closeCode));
        if (!_ready.isCompleted) {
          _ready.completeError(StateError('流式语音服务不可用'));
        } else if (_finishRequested && !_final.isCompleted) {
          _final.completeError(VoiceStreamClosedException(_channel.closeCode));
        }
      },
      cancelOnError: false,
    );
  }

  void _fail(Object error, [StackTrace? stack]) {
    if (!_ready.isCompleted) {
      _ready.completeError(error, stack);
    }
    if (_finishRequested && !_final.isCompleted) {
      _final.completeError(error, stack);
    }
  }

  @override
  bool sendAudio(Uint8List bytes) {
    if (_closed || _finishRequested || bytes.isEmpty) return false;
    if (!_ready.isCompleted) return false;
    _channel.sink.add(bytes);
    return true;
  }

  @override
  Future<String> finish() async {
    if (_closed || !_ready.isCompleted) {
      await _ready.future;
    }
    if (_closed) throw VoiceStreamClosedException(_closeCode);
    if (!_finishRequested) {
      _finishRequested = true;
      _channel.sink.add(jsonEncode(<String, String>{'event': 'stop'}));
      _finalTimer = Timer(const Duration(seconds: 15), () {
        if (!_final.isCompleted) {
          _final.completeError(StateError('流式语音识别结果超时'));
          unawaited(close());
        }
      });
    }
    return _final.future;
  }

  @override
  Future<void> cancel() async {
    if (_closed) return;
    _finishRequested = true;
    if (_ready.isCompleted) {
      _channel.sink.add(jsonEncode(<String, String>{'event': 'cancel'}));
    }
    await close();
  }

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _readyTimer?.cancel();
    _finalTimer?.cancel();
    await _channel.sink.close(status.normalClosure);
    await _events.close();
  }
}

class VoiceStreamClosedException implements Exception {
  const VoiceStreamClosedException(this.closeCode);

  final int? closeCode;

  @override
  String toString() => 'Voice stream closed (code: $closeCode)';
}
