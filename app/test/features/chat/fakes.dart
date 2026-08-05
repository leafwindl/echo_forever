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

class FakeChatRepository implements ChatRepository {
  FakeChatRepository({this.onSend, this.onSendSticker, this.onClear});

  SendChatHandler? onSend;
  SendStickerHandler? onSendSticker;
  ClearChatHandler? onClear;
  int sendCalls = 0;
  int sendStickerCalls = 0;
  int clearCalls = 0;
  final List<String> sentMessages = <String>[];
  final List<ChatSticker> sentStickers = <ChatSticker>[];
  ChatCancellation? lastCancellation;

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
