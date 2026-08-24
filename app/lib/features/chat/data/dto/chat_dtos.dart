class AsyncChatMessageRequestDto {
  const AsyncChatMessageRequestDto.text({
    required this.clientMessageId,
    required this.text,
  }) : messageType = 'text',
       stickerId = '';

  const AsyncChatMessageRequestDto.sticker({
    required this.clientMessageId,
    required this.stickerId,
  }) : messageType = 'sticker',
       text = '',
       assert(stickerId != '');

  final String clientMessageId;
  final String messageType;
  final String text;
  final String stickerId;

  Map<String, Object?> toJson() => <String, Object?>{
    'client_message_id': clientMessageId,
    'message_type': messageType,
    if (text.isNotEmpty) 'text': text,
    if (stickerId.isNotEmpty) 'sticker_id': stickerId,
  };
}

class ChatHistoryResponseDto {
  const ChatHistoryResponseDto({
    required this.conversationId,
    required this.items,
    required this.hasMore,
    this.nextBeforeId,
    this.nextAfterId,
  });

  factory ChatHistoryResponseDto.fromJson(Map<String, dynamic> json) {
    return ChatHistoryResponseDto(
      conversationId: json['conversation_id'] as String? ?? '',
      items: _mapList(json['items'], ChatHistoryMessageDto.fromJson),
      hasMore: json['has_more'] as bool? ?? false,
      nextBeforeId: json['next_before_id'] as int?,
      nextAfterId: json['next_after_id'] as int?,
    );
  }

  final String conversationId;
  final List<ChatHistoryMessageDto> items;
  final bool hasMore;
  final int? nextBeforeId;
  final int? nextAfterId;
}

class ChatHistoryMessageDto {
  const ChatHistoryMessageDto({
    required this.messageId,
    required this.stableMessageId,
    required this.clientMessageId,
    required this.role,
    required this.messageType,
    required this.content,
    required this.contentParts,
    required this.sources,
    required this.agentTurnId,
    required this.replyGroupId,
    required this.sequenceInGroup,
    required this.inReplyToMessageId,
    required this.createdAt,
  });

  factory ChatHistoryMessageDto.fromJson(Map<String, dynamic> json) {
    return ChatHistoryMessageDto(
      messageId: json['message_id'] as int,
      stableMessageId: json['stable_message_id'] as String? ?? '',
      clientMessageId: json['client_message_id'] as String? ?? '',
      role: json['role'] as String? ?? 'assistant',
      messageType: json['message_type'] as String? ?? 'text',
      content: json['content'] as String? ?? '',
      contentParts: _mapList(
        json['content_parts'],
        ChatContentPartDto.fromJson,
      ),
      sources: _mapList(json['sources'], ChatSourceDto.fromJson),
      agentTurnId: json['agent_turn_id'] as String? ?? '',
      replyGroupId: json['reply_group_id'] as String? ?? '',
      sequenceInGroup: json['sequence_in_group'] as int? ?? 0,
      inReplyToMessageId: json['in_reply_to_message_id'] as int?,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
    );
  }

  final int messageId;
  final String stableMessageId;
  final String clientMessageId;
  final String role;
  final String messageType;
  final String content;
  final List<ChatContentPartDto> contentParts;
  final List<ChatSourceDto> sources;
  final String agentTurnId;
  final String replyGroupId;
  final int sequenceInGroup;
  final int? inReplyToMessageId;
  final DateTime? createdAt;
}

class ChatAcceptedTurnDto {
  const ChatAcceptedTurnDto({required this.turnId, required this.status});

  factory ChatAcceptedTurnDto.fromJson(Map<String, dynamic> json) {
    return ChatAcceptedTurnDto(
      turnId: json['turn_id'] as String? ?? '',
      status: json['status'] as String? ?? '',
    );
  }

  final String turnId;
  final String status;
}

class ChatMessageAcceptanceDto {
  const ChatMessageAcceptanceDto({
    required this.conversationId,
    required this.message,
    required this.turn,
    required this.replayed,
  });

  factory ChatMessageAcceptanceDto.fromJson(Map<String, dynamic> json) {
    return ChatMessageAcceptanceDto(
      conversationId: json['conversation_id'] as String? ?? '',
      message: ChatHistoryMessageDto.fromJson(
        Map<String, dynamic>.from(
          json['message'] as Map? ?? const <String, dynamic>{},
        ),
      ),
      turn: ChatAcceptedTurnDto.fromJson(
        Map<String, dynamic>.from(
          json['turn'] as Map? ?? const <String, dynamic>{},
        ),
      ),
      replayed: json['replayed'] as bool? ?? false,
    );
  }

  final String conversationId;
  final ChatHistoryMessageDto message;
  final ChatAcceptedTurnDto turn;
  final bool replayed;
}

class ChatDeliveryPresentationDto {
  const ChatDeliveryPresentationDto({
    required this.agentElapsedMs,
    required this.initialDelayMs,
    required this.messageDelaysMs,
  });

  factory ChatDeliveryPresentationDto.fromJson(Map<String, dynamic> json) {
    return ChatDeliveryPresentationDto(
      agentElapsedMs: json['agent_elapsed_ms'] as int? ?? 0,
      initialDelayMs: json['initial_delay_ms'] as int? ?? 0,
      messageDelaysMs: _intList(json['message_delays_ms']),
    );
  }

  final int agentElapsedMs;
  final int initialDelayMs;
  final List<int> messageDelaysMs;
}

class ChatEventDto {
  const ChatEventDto({required this.event, required this.data});

  final String event;
  final Map<String, dynamic> data;
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

List<int> _intList(Object? value) {
  if (value is! List) {
    return const <int>[];
  }
  return value
      .whereType<num>()
      .map((item) => item.toInt())
      .toList(growable: false);
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
