import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:echo_app/features/call/data/web_socket_voice_client.dart';
import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late _VoiceTestServer server;

  setUp(() async {
    server = _VoiceTestServer();
    await server.start();
  });

  tearDown(() async {
    await server.close();
  });

  test('opens the native socket and parses a ready message', () async {
    final session = await _openSession(server);

    final event = await _nextEvent(session, VoiceStreamEventType.ready);
    expect(event.type, VoiceStreamEventType.ready);
    expect(server.authorization, 'Bearer test-access');
    expect(server.requestId, 'request-1');

    await session.close();
  });

  test('sends binary audio and parses partial and final events', () async {
    final session = await _openSession(server);
    await _nextEvent(session, VoiceStreamEventType.ready);

    final audio = Uint8List.fromList(<int>[1, 2, 3, 4]);
    expect(session.sendAudio(audio), isTrue);
    await server.audioReceived.future.timeout(const Duration(seconds: 1));
    expect(server.audio, <int>[1, 2, 3, 4]);

    final eventsFuture = session.events
        .where(
          (event) =>
              event.type == VoiceStreamEventType.partial ||
              event.type == VoiceStreamEventType.finalResult,
        )
        .take(2)
        .toList();
    server.socket!.add(
      jsonEncode(<String, String>{'type': 'partial', 'text': ' 你好 '}),
    );
    server.socket!.add(
      jsonEncode(<String, String>{'type': 'final', 'text': ' 你好世界 '}),
    );

    final events = await eventsFuture.timeout(const Duration(seconds: 2));
    expect(events.map((event) => event.type), <VoiceStreamEventType>[
      VoiceStreamEventType.partial,
      VoiceStreamEventType.finalResult,
    ]);
    expect(events.map((event) => event.text), <String>['你好', '你好世界']);

    await session.close();
  });

  test('finish sends a stop control frame and returns final text', () async {
    final session = await _openSession(server);
    await _nextEvent(session, VoiceStreamEventType.ready);

    final result = await session.finish();

    expect(result, '识别完成');
    await server.stopReceived.future.timeout(const Duration(seconds: 1));
    expect(server.controls, <String>['stop']);
  });

  test('emits a closed event when the peer closes the connection', () async {
    final session = await _openSession(server);
    await _nextEvent(session, VoiceStreamEventType.ready);

    final closed = _nextEvent(session, VoiceStreamEventType.closed);
    await server.socket!.close(WebSocketStatus.normalClosure, 'done');

    final event = await closed;
    expect(event.closeCode, WebSocketStatus.normalClosure);
    expect(session.sendAudio(Uint8List.fromList(<int>[1])), isFalse);
  });
}

Future<VoiceSocketSession> _openSession(_VoiceTestServer server) async {
  final client = WebSocketVoiceClient(
    baseUrl: 'http://127.0.0.1:${server.port}',
    accessToken: 'test-access',
  );
  return client.open(requestId: 'request-1');
}

Future<VoiceStreamEvent> _nextEvent(
  VoiceSocketSession session,
  VoiceStreamEventType type,
) {
  return session.events
      .firstWhere((event) => event.type == type)
      .timeout(const Duration(seconds: 2));
}

class _VoiceTestServer {
  HttpServer? _server;
  WebSocket? socket;
  String? authorization;
  String? requestId;
  final List<int> audio = <int>[];
  final List<String> controls = <String>[];
  final Completer<void> audioReceived = Completer<void>();
  final Completer<void> stopReceived = Completer<void>();

  int get port => _server!.port;

  Future<void> start() async {
    _server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _server!.listen((request) async {
      if (request.uri.path != '/voice/asr/stream') {
        request.response.statusCode = HttpStatus.notFound;
        await request.response.close();
        return;
      }
      authorization = request.headers.value(HttpHeaders.authorizationHeader);
      requestId = request.headers.value('x-request-id');
      final upgraded = await WebSocketTransformer.upgrade(request);
      socket = upgraded;
      upgraded.listen((message) {
        if (message is Uint8List) {
          audio.addAll(message);
          if (!audioReceived.isCompleted) audioReceived.complete();
          return;
        }
        if (message is List<int>) {
          audio.addAll(message);
          if (!audioReceived.isCompleted) audioReceived.complete();
          return;
        }
        if (message is! String) return;
        final payload = jsonDecode(message) as Map<String, dynamic>;
        final event = payload['event'];
        if (event is! String) return;
        controls.add(event);
        if (event == 'stop') {
          if (!stopReceived.isCompleted) stopReceived.complete();
          upgraded.add(
            jsonEncode(<String, String>{'type': 'final', 'text': '识别完成'}),
          );
        }
      });
      await Future<void>.delayed(const Duration(milliseconds: 20));
      upgraded.add(jsonEncode(<String, String>{'type': 'ready'}));
    });
  }

  Future<void> close() async {
    try {
      await socket?.close(WebSocketStatus.normalClosure);
    } on Object {
      // The peer may already have closed during a test.
    }
    await _server?.close(force: true);
  }
}
