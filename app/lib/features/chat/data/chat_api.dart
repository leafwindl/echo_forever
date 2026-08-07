import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/chat/data/dto/chat_dtos.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';

class ChatApi {
  const ChatApi(this._client);

  static const sendPath = '/chat/send';
  static const messagesPath = '/chat/messages';
  static const eventsPath = '/chat/events';
  static const clearPath = '/chat/clear';

  final DioClient _client;

  Future<ChatHistoryResponseDto> loadHistory({
    int? beforeId,
    int? afterId,
    int limit = 10,
    ChatCancellation? cancellation,
  }) async {
    final queryParameters = <String, dynamic>{'limit': limit};
    if (beforeId != null) {
      queryParameters['before_id'] = beforeId;
    }
    if (afterId != null) {
      queryParameters['after_id'] = afterId;
    }
    final response = await _client.get<Map<String, dynamic>>(
      messagesPath,
      queryParameters: queryParameters,
      cancelToken: _bindCancellation(cancellation),
    );
    return ChatHistoryResponseDto.fromJson(response.data!);
  }

  Future<ChatMessageAcceptanceDto> acceptMessage(
    AsyncChatMessageRequestDto request, {
    ChatCancellation? cancellation,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      messagesPath,
      data: request.toJson(),
      cancelToken: _bindCancellation(cancellation),
    );
    return ChatMessageAcceptanceDto.fromJson(response.data!);
  }

  Stream<ChatEventDto> watchEvents({
    required int afterMessageId,
    ChatCancellation? cancellation,
  }) async* {
    final cancelToken = _bindCancellation(cancellation) ?? CancelToken();
    try {
      final response = await _client.get<ResponseBody>(
        eventsPath,
        queryParameters: <String, dynamic>{'after_message_id': afterMessageId},
        options: Options(
          responseType: ResponseType.stream,
          receiveTimeout: Duration.zero,
          headers: const <String, dynamic>{'Accept': 'text/event-stream'},
        ),
        cancelToken: cancelToken,
      );
      final body = response.data;
      if (body == null) {
        throw const AppException(kind: AppExceptionKind.unexpected);
      }
      var eventName = '';
      final dataLines = <String>[];
      await for (final line
          in utf8.decoder.bind(body.stream).transform(const LineSplitter())) {
        if (line.isEmpty) {
          final event = _parseEventFields(eventName, dataLines);
          if (event != null) yield event;
          eventName = '';
          dataLines.clear();
          continue;
        }
        if (line.startsWith('event:')) {
          eventName = line.substring(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.add(line.substring(5).trimLeft());
        }
      }
      final trailingEvent = _parseEventFields(eventName, dataLines);
      if (trailingEvent != null) {
        yield trailingEvent;
      }
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    } finally {
      if (!cancelToken.isCancelled) {
        cancelToken.cancel('chat event stream closed');
      }
    }
  }

  Future<ChatResponseDto> sendMessage(
    ChatRequestDto request, {
    ChatCancellation? cancellation,
  }) async {
    final cancelToken = _bindCancellation(cancellation);
    final response = await _client.post<Map<String, dynamic>>(
      sendPath,
      data: request.toJson(),
      options: Options(receiveTimeout: const Duration(seconds: 120)),
      cancelToken: cancelToken,
    );
    return ChatResponseDto.fromJson(response.data!);
  }

  Future<ClearChatResponseDto> clearContext({
    ChatCancellation? cancellation,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      clearPath,
      cancelToken: _bindCancellation(cancellation),
    );
    return ClearChatResponseDto.fromJson(response.data!);
  }

  CancelToken? _bindCancellation(ChatCancellation? cancellation) {
    if (cancellation == null) {
      return null;
    }
    final cancelToken = CancelToken();
    cancellation.whenCancelled(() {
      if (!cancelToken.isCancelled) {
        cancelToken.cancel('chat page disposed');
      }
    });
    return cancelToken;
  }

  ChatEventDto? _parseEventFields(String eventName, List<String> dataLines) {
    if (eventName.isEmpty || dataLines.isEmpty) return null;
    final decoded = jsonDecode(dataLines.join('\n'));
    if (decoded is! Map) return null;
    return ChatEventDto(
      event: eventName,
      data: Map<String, dynamic>.from(decoded),
    );
  }
}
