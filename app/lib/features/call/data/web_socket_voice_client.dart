import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';

/// WebSocket 语音客户端。
///
/// 传输层使用 dart:io 原生 [WebSocket]（不走 web_socket_channel 包），
/// 规避 web_socket_channel 3.x 在 Android 上连接后立即断开的兼容问题。
class WebSocketVoiceClient implements VoiceSocketClient {
  WebSocketVoiceClient({required this.baseUrl, required this.accessToken});

  final String baseUrl;
  final String accessToken;

  @override
  Future<VoiceSocketSession> open({required String requestId}) async {
    final base = Uri.parse(baseUrl);
    final uri = base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: '/voice/asr/stream',
    );
    final socket = await WebSocket.connect(
      uri.toString(),
      headers: <String, String>{
        'Authorization': 'Bearer $accessToken',
        'X-Request-ID': requestId,
      },
    ).timeout(const Duration(seconds: 5));
    return _WebSocketVoiceSession(socket);
  }
}

class _WebSocketVoiceSession implements VoiceSocketSession {
  _WebSocketVoiceSession(this._socket) {
    _listen();
    _readyTimer = Timer(const Duration(seconds: 5), () {
      if (!_ready.isCompleted) {
        _fail(StateError('流式语音服务连接超时'));
        unawaited(close());
      }
    });
  }

  final WebSocket _socket;
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

  void _emit(VoiceStreamEvent event) {
    if (!_events.isClosed) _events.add(event);
  }

  void _listen() {
    _socket.listen(
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
            _emit(const VoiceStreamEvent.ready());
          case 'partial':
            _emit(
              VoiceStreamEvent.partial((json['text'] as String? ?? '').trim()),
            );
          case 'final':
            final text = (json['text'] as String? ?? '').trim();
            _emit(VoiceStreamEvent.finalResult(text));
            if (!_final.isCompleted) _final.complete(text);
            _finalTimer?.cancel();
          case 'error':
            final detail = json['detail'] as String? ?? '流式语音识别失败';
            _emit(VoiceStreamEvent.error(detail, closeCode: _closeCode));
            if (!_final.isCompleted) _final.completeError(StateError(detail));
        }
      },
      onError: (Object error, StackTrace stack) {
        _emit(VoiceStreamEvent.error(error.toString()));
        _fail(error, stack);
      },
      onDone: () {
        _closeCode = _socket.closeCode;
        _closed = true;
        _readyTimer?.cancel();
        _finalTimer?.cancel();
        _emit(VoiceStreamEvent.closed(_closeCode));
        if (!_ready.isCompleted) {
          _ready.completeError(StateError('流式语音服务不可用'));
        } else if (_finishRequested && !_final.isCompleted) {
          _final.completeError(VoiceStreamClosedException(_closeCode));
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
    _socket.add(bytes);
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
      _socket.add(jsonEncode(<String, String>{'event': 'stop'}));
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
      _socket.add(jsonEncode(<String, String>{'event': 'cancel'}));
    }
    await close();
  }

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _readyTimer?.cancel();
    _finalTimer?.cancel();
    try {
      await _socket.close(WebSocketStatus.normalClosure);
    } on Object {
      // 忽略关闭异常：socket 可能已断
    }
    await _events.close();
  }
}

class VoiceStreamClosedException implements Exception {
  const VoiceStreamClosedException(this.closeCode);

  final int? closeCode;
}
