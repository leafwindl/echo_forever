import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/interceptors/auth_interceptor.dart';
import 'package:echo_app/core/network/token_refresh_coordinator.dart';
import 'package:echo_app/features/chat/data/chat_api.dart';
import 'package:echo_app/features/chat/data/chat_repository_impl.dart';
import 'package:echo_app/features/chat/data/dto/chat_dtos.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('serializes POST /chat/send with mode=chat', () {
    expect(ChatApi.sendPath, '/chat/send');
    expect(ChatApi.messagesPath, '/chat/messages');
    expect(ChatApi.clearPath, '/chat/clear');
    expect(const ChatRequestDto(message: '你好').toJson(), <String, Object?>{
      'message': '你好',
      'mode': 'chat',
    });
  });

  test('serializes a standalone sticker chat request by sticker id', () {
    expect(
      const ChatRequestDto(
        message: '',
        contentParts: <ChatRequestContentPartDto>[
          ChatRequestContentPartDto.sticker('stk_wave'),
        ],
      ).toJson(),
      <String, Object?>{
        'message': '',
        'mode': 'chat',
        'content_parts': <Map<String, Object?>>[
          <String, Object?>{'type': 'sticker', 'sticker_id': 'stk_wave'},
        ],
      },
    );
  });

  test('parses the complete backend chat response schema', () {
    final response = ChatResponseDto.fromJson(<String, dynamic>{
      'reply': '一起去散步吧。',
      'audio_urls': <String>['https://cdn.example.test/reply.mp3'],
      'content_parts': <Map<String, Object?>>[
        <String, Object?>{
          'type': 'text',
          'text': '一起去散步吧。',
          'sticker_id': '',
          'url': '',
        },
        <String, Object?>{
          'type': 'sticker',
          'text': '',
          'sticker_id': 'wave',
          'url': 'https://cdn.example.test/wave.png',
        },
      ],
      'sources': <Map<String, Object?>>[
        <String, Object?>{
          'title': 'Echo 来源',
          'url': 'https://example.test/source',
          'snippet': '摘要',
          'published_at': '2026-08-04T08:00:00Z',
        },
      ],
    });

    expect(response.reply, '一起去散步吧。');
    expect(response.audioUrls, <String>['https://cdn.example.test/reply.mp3']);
    expect(response.contentParts, hasLength(2));
    expect(response.contentParts.last.type, 'sticker');
    expect(response.contentParts.last.stickerId, 'wave');
    expect(response.sources.single.snippet, '摘要');
    expect(response.sources.single.publishedAt, '2026-08-04T08:00:00Z');
  });

  test('parses clear counts and defaults optional response arrays', () {
    final response = ChatResponseDto.fromJson(<String, dynamic>{'reply': '收到'});
    final cleared = ClearChatResponseDto.fromJson(<String, dynamic>{
      'deleted_messages': 7,
      'reset_conversations': 2,
    });

    expect(response.audioUrls, isEmpty);
    expect(response.contentParts, isEmpty);
    expect(response.sources, isEmpty);
    expect(cleared.deletedMessages, 7);
    expect(cleared.resetConversations, 2);
  });

  test('parses paged chat history with standalone sticker messages', () async {
    final client = _CapturingDioClient();

    final response = await ChatApi(client).loadHistory(beforeId: 42, limit: 10);
    final page = await ChatRepositoryImpl(
      ChatApi(client),
    ).loadHistory(beforeId: 42, limit: 10);

    expect(client.getPath, '/chat/messages');
    expect(client.getQuery, <String, dynamic>{'limit': 10, 'before_id': 42});
    expect(response.conversationId, 'conv-history');
    expect(response.nextBeforeId, 20);
    expect(page.messages.single.id, 20);
    expect(page.messages.single.sender, ChatMessageSender.user);
    expect(page.messages.single.content, isEmpty);
    expect(page.messages.single.sticker?.stickerId, 'stk-wave');
  });

  test('only accepts http and https source URLs', () {
    expect(
      const ChatSource(title: 'safe', url: 'https://example.test').safeUri,
      Uri.parse('https://example.test'),
    );
    expect(
      const ChatSource(title: 'unsafe', url: 'javascript:alert(1)').safeUri,
      isNull,
    );
    expect(
      const ChatSource(title: 'unsafe', url: 'file:///tmp/a').safeUri,
      isNull,
    );
  });

  test('binds page cancellation to the Dio request token', () async {
    final client = _CapturingDioClient();
    final cancellation = ChatCancellation();
    final response = ChatApi(client).sendMessage(
      const ChatRequestDto(message: '你好'),
      cancellation: cancellation,
    );

    cancellation.cancel();

    expect(client.cancelToken, isNotNull);
    expect(client.cancelToken!.isCancelled, isTrue);
    expect((await response).reply, 'captured');
  });

  test(
    'authenticated chat request refreshes and replays one 401 once',
    () async {
      final adapter = _QueueAdapter(<int>[401, 200]);
      final dio = Dio(BaseOptions(baseUrl: 'https://echo.example.test'))
        ..httpClientAdapter = adapter;
      var snapshot = _session('old-access');
      var refreshCalls = 0;
      final coordinator = TokenRefreshCoordinator(
        readSession: () => snapshot,
        refreshSession: (_, _) async {
          refreshCalls += 1;
          return _session('new-access');
        },
        persistSession: (value) async => snapshot = value,
        clearSession: (_) async {},
        markSessionOffline: () {},
      );
      dio.interceptors.add(
        AuthInterceptor(
          dio: dio,
          readSession: () => snapshot,
          refreshCoordinator: coordinator,
        ),
      );

      final response = await ChatApi(
        DioClient(dio),
      ).sendMessage(const ChatRequestDto(message: '你好'));

      expect(response.reply, 'Echo reply');
      expect(adapter.calls, 2);
      expect(refreshCalls, 1);
      expect(adapter.authorizationHeaders, <String>[
        'bearer old-access',
        'bearer new-access',
      ]);
    },
  );

  test('a repeated 401 is not replayed more than once', () async {
    final adapter = _QueueAdapter(<int>[401, 401, 200]);
    final dio = Dio(BaseOptions(baseUrl: 'https://echo.example.test'))
      ..httpClientAdapter = adapter;
    var snapshot = _session('old-access');
    var refreshCalls = 0;
    final coordinator = TokenRefreshCoordinator(
      readSession: () => snapshot,
      refreshSession: (_, _) async {
        refreshCalls += 1;
        return _session('new-access');
      },
      persistSession: (value) async => snapshot = value,
      clearSession: (_) async {},
      markSessionOffline: () {},
    );
    dio.interceptors.add(
      AuthInterceptor(
        dio: dio,
        readSession: () => snapshot,
        refreshCoordinator: coordinator,
      ),
    );

    await expectLater(
      ChatApi(DioClient(dio)).sendMessage(const ChatRequestDto(message: '你好')),
      throwsA(anything),
    );
    expect(adapter.calls, 2);
    expect(refreshCalls, 1);
  });
}

SessionSnapshot _session(String accessToken) {
  return SessionSnapshot.authenticated(
    userId: 'phone-user',
    accessToken: accessToken,
    refreshToken: 'refresh-token',
    tokenType: 'bearer',
    accessExpiresAt: DateTime.now().toUtc().add(const Duration(hours: 1)),
    refreshExpiresAt: DateTime.now().toUtc().add(const Duration(days: 30)),
    deviceId: 'device-id',
  );
}

class _QueueAdapter implements HttpClientAdapter {
  _QueueAdapter(this._statuses);

  final List<int> _statuses;
  int calls = 0;
  final List<String> authorizationHeaders = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    authorizationHeaders.add(options.headers['Authorization'] as String);
    final status = _statuses[calls];
    calls += 1;
    final body = status == 200
        ? <String, Object?>{
            'reply': 'Echo reply',
            'audio_urls': <String>[],
            'content_parts': <Object>[],
            'sources': <Object>[],
          }
        : <String, Object?>{'detail': 'unauthorized'};
    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

class _CapturingDioClient extends DioClient {
  _CapturingDioClient() : super(Dio());

  CancelToken? cancelToken;
  String? getPath;
  Map<String, dynamic>? getQuery;

  @override
  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) {
    getPath = path;
    getQuery = queryParameters;
    return Future<Response<T>>.value(
      Response<T>(
        data:
            <String, dynamic>{
                  'conversation_id': 'conv-history',
                  'items': <Map<String, Object?>>[
                    <String, Object?>{
                      'message_id': 20,
                      'role': 'user',
                      'message_type': 'sticker',
                      'content': '',
                      'content_parts': <Map<String, Object?>>[
                        <String, Object?>{
                          'type': 'sticker',
                          'sticker_id': 'stk-wave',
                          'url': 'https://cdn.example.test/wave.png',
                        },
                      ],
                      'created_at': '2026-08-06T08:00:00Z',
                    },
                  ],
                  'has_more': true,
                  'next_before_id': 20,
                }
                as T,
        requestOptions: RequestOptions(path: path),
      ),
    );
  }

  @override
  Future<Response<T>> post<T>(
    String path, {
    Object? data,
    Options? options,
    CancelToken? cancelToken,
  }) {
    this.cancelToken = cancelToken;
    return Future<Response<T>>.value(
      Response<T>(
        data:
            <String, dynamic>{
                  'reply': 'captured',
                  'audio_urls': <String>[],
                  'content_parts': <Object>[],
                  'sources': <Object>[],
                }
                as T,
        requestOptions: RequestOptions(path: path),
      ),
    );
  }
}
