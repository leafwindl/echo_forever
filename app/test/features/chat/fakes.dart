import 'dart:async';

import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';

typedef AcceptTextHandler =
    Future<ChatMessageAcceptance> Function(
      String message,
      String clientMessageId,
      ChatCancellation? cancellation,
    );
typedef AcceptStickerHandler =
    Future<ChatMessageAcceptance> Function(
      ChatSticker sticker,
      String clientMessageId,
      ChatCancellation? cancellation,
    );
typedef ClearChatHandler =
    Future<ClearChatResult> Function(ChatCancellation? cancellation);
typedef LoadHistoryHandler =
    Future<ChatHistoryPage> Function(
      int? beforeId,
      int? afterId,
      int limit,
      ChatCancellation? cancellation,
    );

class FakeChatRepository implements ChatRepository {
  FakeChatRepository({
    this.onLoadHistory,
    this.onAcceptText,
    this.onAcceptSticker,
    this.onClear,
  });

  LoadHistoryHandler? onLoadHistory;
  AcceptTextHandler? onAcceptText;
  AcceptStickerHandler? onAcceptSticker;
  ClearChatHandler? onClear;
  int acceptTextCalls = 0;
  int acceptStickerCalls = 0;
  int clearCalls = 0;
  int historyCalls = 0;
  int watchEventCalls = 0;
  int nextServerMessageId = 1;
  final List<int?> historyBeforeIds = <int?>[];
  final List<int?> historyAfterIds = <int?>[];
  final List<String> sentMessages = <String>[];
  final List<ChatSticker> sentStickers = <ChatSticker>[];
  final List<String> clientMessageIds = <String>[];
  final StreamController<ChatEvent> events =
      StreamController<ChatEvent>.broadcast();
  ChatCancellation? lastCancellation;

  @override
  Future<ChatHistoryPage> loadHistory({
    int? beforeId,
    int? afterId,
    int limit = 10,
    ChatCancellation? cancellation,
  }) {
    historyCalls += 1;
    historyBeforeIds.add(beforeId);
    historyAfterIds.add(afterId);
    lastCancellation = cancellation;
    return onLoadHistory?.call(beforeId, afterId, limit, cancellation) ??
        Future<ChatHistoryPage>.value(
          const ChatHistoryPage(
            conversationId: 'conv-fake',
            messages: <ChatMessage>[],
            hasMore: false,
          ),
        );
  }

  @override
  Future<ChatMessageAcceptance> acceptTextMessage(
    String message,
    String clientMessageId, {
    ChatCancellation? cancellation,
  }) {
    acceptTextCalls += 1;
    sentMessages.add(message);
    clientMessageIds.add(clientMessageId);
    lastCancellation = cancellation;
    return onAcceptText?.call(message, clientMessageId, cancellation) ??
        Future<ChatMessageAcceptance>.value(
          _acceptance(
            ChatMessage(
              id: nextServerMessageId++,
              sender: ChatMessageSender.user,
              content: message,
              clientMessageId: clientMessageId,
              createdAt: DateTime.now(),
            ),
          ),
        );
  }

  @override
  Future<ChatMessageAcceptance> acceptStickerMessage(
    ChatSticker sticker, {
    required String clientMessageId,
    ChatCancellation? cancellation,
  }) {
    acceptStickerCalls += 1;
    sentStickers.add(sticker);
    clientMessageIds.add(clientMessageId);
    lastCancellation = cancellation;
    return onAcceptSticker?.call(sticker, clientMessageId, cancellation) ??
        Future<ChatMessageAcceptance>.value(
          _acceptance(
            ChatMessage(
              id: nextServerMessageId++,
              sender: ChatMessageSender.user,
              content: '',
              sticker: sticker,
              clientMessageId: clientMessageId,
              createdAt: DateTime.now(),
            ),
          ),
        );
  }

  @override
  Stream<ChatEvent> watchEvents({
    required int afterMessageId,
    ChatCancellation? cancellation,
  }) {
    watchEventCalls += 1;
    lastCancellation = cancellation;
    return events.stream;
  }

  void emit(ChatEvent event) => events.add(event);

  @override
  Future<ClearChatResult> clearContext({ChatCancellation? cancellation}) {
    clearCalls += 1;
    lastCancellation = cancellation;
    return onClear?.call(cancellation) ??
        Future<ClearChatResult>.value(
          const ClearChatResult(deletedMessages: 2, resetConversations: 1),
        );
  }

  ChatMessageAcceptance _acceptance(ChatMessage message) {
    return ChatMessageAcceptance(
      conversationId: 'conv-fake',
      message: message,
      turn: const ChatAcceptedTurn(turnId: 'turn-fake', status: 'collecting'),
    );
  }
}
