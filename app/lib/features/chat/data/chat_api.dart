import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/chat/data/dto/chat_dtos.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';

class ChatApi {
  const ChatApi(this._client);

  static const sendPath = '/chat/send';
  static const clearPath = '/chat/clear';

  final DioClient _client;

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
}
