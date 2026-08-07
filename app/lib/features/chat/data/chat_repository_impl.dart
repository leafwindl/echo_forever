import 'package:echo_app/features/chat/data/chat_api.dart';
import 'package:echo_app/features/chat/data/dto/chat_dtos.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';

class ChatRepositoryImpl implements ChatRepository {
  const ChatRepositoryImpl(this._api);

  final ChatApi _api;

  @override
  Future<ChatHistoryPage> loadHistory({
    int? beforeId,
    int? afterId,
    int limit = 10,
    ChatCancellation? cancellation,
  }) async {
    final response = await _api.loadHistory(
      beforeId: beforeId,
      afterId: afterId,
      limit: limit,
      cancellation: cancellation,
    );
    return ChatHistoryPage(
      conversationId: response.conversationId,
      messages: response.items.map(_toHistoryMessage).toList(growable: false),
      hasMore: response.hasMore,
      nextBeforeId: response.nextBeforeId,
      nextAfterId: response.nextAfterId,
    );
  }

  @override
  Future<ChatMessageAcceptance> acceptTextMessage(
    String message,
    String clientMessageId, {
    ChatCancellation? cancellation,
  }) async {
    final response = await _api.acceptMessage(
      AsyncChatMessageRequestDto.text(
        clientMessageId: clientMessageId,
        text: message,
      ),
      cancellation: cancellation,
    );
    return _toAcceptance(response);
  }

  @override
  Future<ChatMessageAcceptance> acceptStickerMessage(
    ChatSticker sticker, {
    required String clientMessageId,
    ChatCancellation? cancellation,
  }) async {
    final response = await _api.acceptMessage(
      AsyncChatMessageRequestDto.sticker(
        clientMessageId: clientMessageId,
        stickerId: sticker.stickerId,
      ),
      cancellation: cancellation,
    );
    return _toAcceptance(response);
  }

  @override
  Stream<ChatEvent> watchEvents({
    required int afterMessageId,
    ChatCancellation? cancellation,
  }) {
    return _api
        .watchEvents(afterMessageId: afterMessageId, cancellation: cancellation)
        .map(_toEvent);
  }

  @override
  Future<ClearChatResult> clearContext({ChatCancellation? cancellation}) async {
    final response = await _api.clearContext(cancellation: cancellation);
    return ClearChatResult(
      deletedMessages: response.deletedMessages,
      resetConversations: response.resetConversations,
    );
  }

  ChatMessageAcceptance _toAcceptance(ChatMessageAcceptanceDto response) {
    return ChatMessageAcceptance(
      conversationId: response.conversationId,
      message: _toHistoryMessage(response.message),
      turn: ChatAcceptedTurn(
        turnId: response.turn.turnId,
        status: response.turn.status,
      ),
      replayed: response.replayed,
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

  ChatMessage _toHistoryMessage(ChatHistoryMessageDto dto) {
    ChatSticker? sticker;
    for (final part in dto.contentParts) {
      final mappedPart = _toContentPart(part);
      if (mappedPart.sticker case final ChatSticker historySticker) {
        sticker = historySticker;
        break;
      }
    }
    return ChatMessage(
      id: dto.messageId,
      sender: dto.role == 'user'
          ? ChatMessageSender.user
          : ChatMessageSender.assistant,
      content: dto.messageType == 'sticker' ? '' : dto.content,
      sticker: sticker,
      sources: dto.sources
          .map(_toSource)
          .where((source) => source.safeUri != null)
          .toList(growable: false),
      createdAt: dto.createdAt,
      stableMessageId: dto.stableMessageId,
      clientMessageId: dto.clientMessageId,
      agentTurnId: dto.agentTurnId,
      replyGroupId: dto.replyGroupId,
      sequenceInGroup: dto.sequenceInGroup,
      inReplyToMessageId: dto.inReplyToMessageId,
    );
  }

  ChatEvent _toEvent(ChatEventDto dto) {
    final messages = _mapEventMessages(dto.data['messages']);
    final presentationData = dto.data['presentation'];
    final presentation = presentationData is Map
        ? ChatDeliveryPresentationDto.fromJson(
            Map<String, dynamic>.from(presentationData),
          )
        : const ChatDeliveryPresentationDto(
            agentElapsedMs: 0,
            initialDelayMs: 0,
            messageDelaysMs: <int>[],
          );
    return ChatEvent(
      type: switch (dto.event) {
        'chat.ready' => ChatEventType.ready,
        'chat.sync' => ChatEventType.sync,
        'chat.typing.started' => ChatEventType.typingStarted,
        'chat.typing.stopped' => ChatEventType.typingStopped,
        'chat.delivery.created' => ChatEventType.delivery,
        'chat.turn.failed' => ChatEventType.turnFailed,
        'chat.conversation.reset' => ChatEventType.conversationReset,
        _ => ChatEventType.heartbeat,
      },
      conversationId: dto.data['conversation_id'] as String? ?? '',
      turnId: dto.data['turn_id'] as String? ?? '',
      echoTyping: dto.data['echo_typing'] as bool? ?? false,
      messages: messages,
      presentation: ChatDeliveryPresentation(
        agentElapsedMs: presentation.agentElapsedMs,
        initialDelayMs: presentation.initialDelayMs,
        messageDelaysMs: presentation.messageDelaysMs,
      ),
      errorCode: dto.data['error_code'] as String?,
    );
  }

  List<ChatMessage> _mapEventMessages(Object? value) {
    if (value is! List) return const <ChatMessage>[];
    return value
        .whereType<Map>()
        .map(
          (item) => _toHistoryMessage(
            ChatHistoryMessageDto.fromJson(Map<String, dynamic>.from(item)),
          ),
        )
        .toList(growable: false);
  }
}
