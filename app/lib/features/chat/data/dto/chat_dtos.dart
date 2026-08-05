class ChatRequestDto {
  const ChatRequestDto({
    required this.message,
    this.mode = 'chat',
    this.contentParts = const <ChatRequestContentPartDto>[],
  });

  final String message;
  final String mode;
  final List<ChatRequestContentPartDto> contentParts;

  Map<String, Object?> toJson() => <String, Object?>{
    'message': message,
    'mode': mode,
    if (contentParts.isNotEmpty)
      'content_parts': contentParts.map((part) => part.toJson()).toList(),
  };
}

class ChatRequestContentPartDto {
  const ChatRequestContentPartDto.sticker(this.stickerId) : type = 'sticker';

  final String type;
  final String stickerId;

  Map<String, Object?> toJson() => <String, Object?>{
    'type': type,
    'sticker_id': stickerId,
  };
}

class ChatResponseDto {
  const ChatResponseDto({
    required this.reply,
    required this.audioUrls,
    required this.contentParts,
    required this.sources,
  });

  factory ChatResponseDto.fromJson(Map<String, dynamic> json) {
    return ChatResponseDto(
      reply: json['reply'] as String? ?? '',
      audioUrls: _stringList(json['audio_urls']),
      contentParts: _mapList(
        json['content_parts'],
        ChatContentPartDto.fromJson,
      ),
      sources: _mapList(json['sources'], ChatSourceDto.fromJson),
    );
  }

  final String reply;
  final List<String> audioUrls;
  final List<ChatContentPartDto> contentParts;
  final List<ChatSourceDto> sources;
}

class ChatContentPartDto {
  const ChatContentPartDto({
    required this.type,
    required this.text,
    required this.stickerId,
    required this.url,
  });

  factory ChatContentPartDto.fromJson(Map<String, dynamic> json) {
    return ChatContentPartDto(
      type: json['type'] as String? ?? 'text',
      text: json['text'] as String? ?? '',
      stickerId: json['sticker_id'] as String? ?? '',
      url: json['url'] as String? ?? '',
    );
  }

  final String type;
  final String text;
  final String stickerId;
  final String url;
}

class ChatSourceDto {
  const ChatSourceDto({
    required this.title,
    required this.url,
    required this.snippet,
    this.publishedAt,
  });

  factory ChatSourceDto.fromJson(Map<String, dynamic> json) {
    return ChatSourceDto(
      title: json['title'] as String? ?? '',
      url: json['url'] as String? ?? '',
      snippet: json['snippet'] as String? ?? '',
      publishedAt: json['published_at'] as String?,
    );
  }

  final String title;
  final String url;
  final String snippet;
  final String? publishedAt;
}

class ClearChatResponseDto {
  const ClearChatResponseDto({
    required this.deletedMessages,
    required this.resetConversations,
  });

  factory ClearChatResponseDto.fromJson(Map<String, dynamic> json) {
    return ClearChatResponseDto(
      deletedMessages: json['deleted_messages'] as int,
      resetConversations: json['reset_conversations'] as int,
    );
  }

  final int deletedMessages;
  final int resetConversations;
}

List<String> _stringList(Object? value) {
  if (value is! List) {
    return const <String>[];
  }
  return value.whereType<String>().toList(growable: false);
}

List<T> _mapList<T>(Object? value, T Function(Map<String, dynamic>) fromJson) {
  if (value is! List) {
    return <T>[];
  }
  return value
      .whereType<Map>()
      .map((item) => fromJson(Map<String, dynamic>.from(item)))
      .toList(growable: false);
}
