import 'package:echo_app/features/chat/data/chat_api.dart';
import 'package:echo_app/features/chat/data/dto/chat_dtos.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';

class ChatRepositoryImpl implements ChatRepository {
  const ChatRepositoryImpl(this._api);

  final ChatApi _api;

  @override
  Future<ChatReply> sendMessage(
    String message, {
    ChatCancellation? cancellation,
  }) async {
    final response = await _api.sendMessage(
      ChatRequestDto(message: message),
      cancellation: cancellation,
    );
    return _toReply(response);
  }

  @override
  Future<ChatReply> sendSticker(
    ChatSticker sticker, {
    ChatCancellation? cancellation,
  }) async {
    final response = await _api.sendMessage(
      ChatRequestDto(
        message: '',
        contentParts: <ChatRequestContentPartDto>[
          ChatRequestContentPartDto.sticker(sticker.stickerId),
        ],
      ),
      cancellation: cancellation,
    );
    return _toReply(response);
  }

  @override
  Future<ClearChatResult> clearContext({ChatCancellation? cancellation}) async {
    final response = await _api.clearContext(cancellation: cancellation);
    return ClearChatResult(
      deletedMessages: response.deletedMessages,
      resetConversations: response.resetConversations,
    );
  }

  ChatReply _toReply(ChatResponseDto response) {
    return ChatReply(
      reply: response.reply,
      audioUrls: response.audioUrls,
      contentParts: response.contentParts.map(_toContentPart).toList(),
      sources: response.sources.map(_toSource).toList(),
    );
  }

  ChatContentPart _toContentPart(ChatContentPartDto dto) {
    return ChatContentPart(
      type: dto.type == 'sticker'
          ? ChatContentPartType.sticker
          : ChatContentPartType.text,
      text: dto.text,
      stickerId: dto.stickerId,
      url: dto.url,
    );
  }

  ChatSource _toSource(ChatSourceDto dto) {
    return ChatSource(
      title: dto.title,
      url: dto.url,
      snippet: dto.snippet,
      publishedAt: dto.publishedAt == null
          ? null
          : DateTime.tryParse(dto.publishedAt!),
    );
  }
}
