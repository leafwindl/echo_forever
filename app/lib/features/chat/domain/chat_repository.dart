import 'package:echo_app/features/chat/domain/chat_message.dart';

class ChatCancellation {
  bool _isCancelled = false;
  final List<void Function()> _listeners = <void Function()>[];

  bool get isCancelled => _isCancelled;

  void whenCancelled(void Function() listener) {
    if (_isCancelled) {
      listener();
      return;
    }
    _listeners.add(listener);
  }

  void cancel() {
    if (_isCancelled) {
      return;
    }
    _isCancelled = true;
    final listeners = List<void Function()>.of(_listeners);
    _listeners.clear();
    for (final listener in listeners) {
      listener();
    }
  }
}

class ClearChatResult {
  const ClearChatResult({
    required this.deletedMessages,
    required this.resetConversations,
  });

  final int deletedMessages;
  final int resetConversations;
}

abstract interface class ChatRepository {
  Future<ChatHistoryPage> loadHistory({
    int? beforeId,
    int? afterId,
    int limit = 10,
    ChatCancellation? cancellation,
  });

  Future<ChatMessageAcceptance> acceptTextMessage(
    String message,
    String clientMessageId, {
    ChatCancellation? cancellation,
  });

  Future<ChatMessageAcceptance> acceptStickerMessage(
    ChatSticker sticker, {
    required String clientMessageId,
    ChatCancellation? cancellation,
  });

  Stream<ChatEvent> watchEvents({
    required int afterMessageId,
    ChatCancellation? cancellation,
  });

  Future<ClearChatResult> clearContext({ChatCancellation? cancellation});
}
