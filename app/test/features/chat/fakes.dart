import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';

typedef SendChatHandler =
    Future<ChatReply> Function(String message, ChatCancellation? cancellation);
typedef SendStickerHandler =
    Future<ChatReply> Function(
      ChatSticker sticker,
      ChatCancellation? cancellation,
    );
typedef ClearChatHandler =
    Future<ClearChatResult> Function(ChatCancellation? cancellation);
typedef LoadHistoryHandler =
    Future<ChatHistoryPage> Function(
      int? beforeId,
      int limit,
      ChatCancellation? cancellation,
    );

class FakeChatRepository implements ChatRepository {
  FakeChatRepository({
    this.onLoadHistory,
    this.onSend,
    this.onSendSticker,
    this.onClear,
  });

  LoadHistoryHandler? onLoadHistory;
  SendChatHandler? onSend;
  SendStickerHandler? onSendSticker;
  ClearChatHandler? onClear;
  int sendCalls = 0;
  int sendStickerCalls = 0;
  int clearCalls = 0;
  int historyCalls = 0;
  final List<int?> historyBeforeIds = <int?>[];
  final List<String> sentMessages = <String>[];
  final List<ChatSticker> sentStickers = <ChatSticker>[];
  ChatCancellation? lastCancellation;

  @override
  Future<ChatHistoryPage> loadHistory({
    int? beforeId,
    int limit = 10,
    ChatCancellation? cancellation,
  }) {
    historyCalls += 1;
    historyBeforeIds.add(beforeId);
    lastCancellation = cancellation;
    return onLoadHistory?.call(beforeId, limit, cancellation) ??
        Future<ChatHistoryPage>.value(
          const ChatHistoryPage(
            conversationId: 'conv-fake',
            messages: <ChatMessage>[],
            hasMore: false,
          ),
        );
  }

  @override
  Future<ChatReply> sendMessage(
    String message, {
    ChatCancellation? cancellation,
  }) {
    sendCalls += 1;
    sentMessages.add(message);
    lastCancellation = cancellation;
    return onSend?.call(message, cancellation) ??
        Future<ChatReply>.value(ChatReply(reply: '回复：$message'));
  }

  @override
  Future<ChatReply> sendSticker(
    ChatSticker sticker, {
    ChatCancellation? cancellation,
  }) {
    sendStickerCalls += 1;
    sentStickers.add(sticker);
    lastCancellation = cancellation;
    return onSendSticker?.call(sticker, cancellation) ??
        Future<ChatReply>.value(const ChatReply(reply: '收到这个表情包了'));
  }

  @override
  Future<ClearChatResult> clearContext({ChatCancellation? cancellation}) {
    clearCalls += 1;
    lastCancellation = cancellation;
    return onClear?.call(cancellation) ??
        Future<ClearChatResult>.value(
          const ClearChatResult(deletedMessages: 2, resetConversations: 1),
        );
  }
}
