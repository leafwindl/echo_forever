enum ChatMessageSender { user, assistant }

enum ChatContentPartType { text, sticker }

class ChatSticker {
  const ChatSticker({required this.stickerId, required this.url});

  final String stickerId;
  final String url;

  Uri? get safeUri => _safeHttpUri(url);
}

class ChatSource {
  const ChatSource({
    required this.title,
    required this.url,
    this.snippet = '',
    this.publishedAt,
  });

  final String title;
  final String url;
  final String snippet;
  final DateTime? publishedAt;

  Uri? get safeUri => _safeHttpUri(url);
}

class ChatContentPart {
  const ChatContentPart({
    required this.type,
    this.text = '',
    this.stickerId = '',
    this.url = '',
  });

  final ChatContentPartType type;
  final String text;
  final String stickerId;
  final String url;

  ChatSticker? get sticker => type == ChatContentPartType.sticker
      ? ChatSticker(stickerId: stickerId, url: url)
      : null;
}

class ChatReply {
  const ChatReply({
    required this.reply,
    this.audioUrls = const <String>[],
    this.contentParts = const <ChatContentPart>[],
    this.sources = const <ChatSource>[],
  });

  final String reply;
  final List<String> audioUrls;
  final List<ChatContentPart> contentParts;
  final List<ChatSource> sources;

  ChatSticker? get firstSticker {
    for (final part in contentParts) {
      final sticker = part.sticker;
      if (sticker != null) {
        return sticker;
      }
    }
    return null;
  }
}

class ChatHistoryPage {
  const ChatHistoryPage({
    required this.conversationId,
    required this.messages,
    required this.hasMore,
    this.nextBeforeId,
  });

  final String conversationId;
  final List<ChatMessage> messages;
  final bool hasMore;
  final int? nextBeforeId;
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.sender,
    required this.content,
    this.isTyping = false,
    this.isError = false,
    this.sticker,
    this.sources = const <ChatSource>[],
    this.createdAt,
  });

  factory ChatMessage.typing({required int id}) {
    return ChatMessage(
      id: id,
      sender: ChatMessageSender.assistant,
      content: '',
      isTyping: true,
    );
  }

  final int id;
  final ChatMessageSender sender;
  final String content;
  final bool isTyping;
  final bool isError;
  final ChatSticker? sticker;
  final List<ChatSource> sources;
  final DateTime? createdAt;
}

Uri? _safeHttpUri(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null || !uri.hasAuthority || uri.host.isEmpty) {
    return null;
  }
  return uri.scheme == 'http' || uri.scheme == 'https' ? uri : null;
}
