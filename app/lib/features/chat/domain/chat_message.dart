enum ChatMessageSender { user, assistant }

enum ChatContentPartType { text, sticker }

enum ChatSendState { sending, sent, failed }

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
    this.nextAfterId,
  });

  final String conversationId;
  final List<ChatMessage> messages;
  final bool hasMore;
  final int? nextBeforeId;
  final int? nextAfterId;
}

class ChatAcceptedTurn {
  const ChatAcceptedTurn({required this.turnId, required this.status});

  final String turnId;
  final String status;
}

class ChatMessageAcceptance {
  const ChatMessageAcceptance({
    required this.conversationId,
    required this.message,
    required this.turn,
    this.replayed = false,
  });

  final String conversationId;
  final ChatMessage message;
  final ChatAcceptedTurn turn;
  final bool replayed;
}

class ChatDeliveryPresentation {
  const ChatDeliveryPresentation({
    this.agentElapsedMs = 0,
    this.initialDelayMs = 0,
    this.messageDelaysMs = const <int>[],
  });

  final int agentElapsedMs;
  final int initialDelayMs;
  final List<int> messageDelaysMs;
}

enum ChatEventType {
  ready,
  sync,
  typingStarted,
  typingStopped,
  delivery,
  turnFailed,
  conversationReset,
  heartbeat,
}

class ChatEvent {
  const ChatEvent({
    required this.type,
    this.conversationId = '',
    this.turnId = '',
    this.echoTyping = false,
    this.messages = const <ChatMessage>[],
    this.presentation = const ChatDeliveryPresentation(),
    this.errorCode,
  });

  final ChatEventType type;
  final String conversationId;
  final String turnId;
  final bool echoTyping;
  final List<ChatMessage> messages;
  final ChatDeliveryPresentation presentation;
  final String? errorCode;
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
    this.stableMessageId = '',
    this.clientMessageId = '',
    this.sendState = ChatSendState.sent,
    this.agentTurnId = '',
    this.replyGroupId = '',
    this.sequenceInGroup = 0,
    this.inReplyToMessageId,
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
  final String stableMessageId;
  final String clientMessageId;
  final ChatSendState sendState;
  final String agentTurnId;
  final String replyGroupId;
  final int sequenceInGroup;
  final int? inReplyToMessageId;

  ChatMessage copyWith({
    int? id,
    ChatMessageSender? sender,
    String? content,
    bool? isTyping,
    bool? isError,
    ChatSticker? sticker,
    bool clearSticker = false,
    List<ChatSource>? sources,
    DateTime? createdAt,
    String? stableMessageId,
    String? clientMessageId,
    ChatSendState? sendState,
    String? agentTurnId,
    String? replyGroupId,
    int? sequenceInGroup,
    int? inReplyToMessageId,
  }) {
    return ChatMessage(
      id: id ?? this.id,
      sender: sender ?? this.sender,
      content: content ?? this.content,
      isTyping: isTyping ?? this.isTyping,
      isError: isError ?? this.isError,
      sticker: clearSticker ? null : sticker ?? this.sticker,
      sources: sources ?? this.sources,
      createdAt: createdAt ?? this.createdAt,
      stableMessageId: stableMessageId ?? this.stableMessageId,
      clientMessageId: clientMessageId ?? this.clientMessageId,
      sendState: sendState ?? this.sendState,
      agentTurnId: agentTurnId ?? this.agentTurnId,
      replyGroupId: replyGroupId ?? this.replyGroupId,
      sequenceInGroup: sequenceInGroup ?? this.sequenceInGroup,
      inReplyToMessageId: inReplyToMessageId ?? this.inReplyToMessageId,
    );
  }
}

Uri? _safeHttpUri(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null || !uri.hasAuthority || uri.host.isEmpty) {
    return null;
  }
  return uri.scheme == 'http' || uri.scheme == 'https' ? uri : null;
}
