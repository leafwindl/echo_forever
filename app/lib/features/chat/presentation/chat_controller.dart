import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/chat/data/chat_providers.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const _emptyReply = '（我刚刚没组织好语言，可以再说一次吗？）';
const _temporaryError = '（我刚刚有点卡住了，等一下再和我说一次好吗？）';

final chatPreferredNameProvider = Provider<String>((ref) {
  return ref.watch(
    personaControllerProvider.select(
      (state) => state.asData?.value.persona.preferredName ?? '',
    ),
  );
});

class ChatState {
  const ChatState({
    required this.messages,
    required this.nextMessageId,
    required this.preferredName,
    this.isSending = false,
    this.isClearing = false,
    this.chatExpanded = false,
    this.errorMessage,
  });

  final List<ChatMessage> messages;
  final int nextMessageId;
  final String preferredName;
  final bool isSending;
  final bool isClearing;
  final bool chatExpanded;
  final String? errorMessage;

  bool get isBusy => isSending || isClearing;

  ChatState copyWith({
    List<ChatMessage>? messages,
    int? nextMessageId,
    String? preferredName,
    bool? isSending,
    bool? isClearing,
    bool? chatExpanded,
    String? errorMessage,
    bool clearError = false,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      nextMessageId: nextMessageId ?? this.nextMessageId,
      preferredName: preferredName ?? this.preferredName,
      isSending: isSending ?? this.isSending,
      isClearing: isClearing ?? this.isClearing,
      chatExpanded: chatExpanded ?? this.chatExpanded,
      errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
    );
  }
}

class ChatController extends Notifier<ChatState> {
  ChatCancellation? _activeCancellation;
  bool _disposed = false;

  @override
  ChatState build() {
    _disposed = false;
    ref.onDispose(() {
      _disposed = true;
      _activeCancellation?.cancel();
      _activeCancellation = null;
    });
    final preferredName = ref.watch(chatPreferredNameProvider).trim();
    return ChatState(
      messages: <ChatMessage>[_greeting(preferredName, 1)],
      nextMessageId: 2,
      preferredName: preferredName,
    );
  }

  Future<bool> sendMessage(String rawMessage) async {
    if (state.isBusy) {
      return false;
    }
    final message = rawMessage.trim();
    if (message.isEmpty || message.length > 2000) {
      return false;
    }

    return _send(
      userContent: message,
      request: (cancellation) => ref
          .read(chatRepositoryProvider)
          .sendMessage(message, cancellation: cancellation),
    );
  }

  Future<bool> sendSticker(ChatSticker sticker) async {
    if (state.isBusy || sticker.stickerId.isEmpty || sticker.safeUri == null) {
      return false;
    }

    return _send(
      userSticker: sticker,
      request: (cancellation) => ref
          .read(chatRepositoryProvider)
          .sendSticker(sticker, cancellation: cancellation),
    );
  }

  Future<bool> _send({
    String userContent = '',
    ChatSticker? userSticker,
    required Future<ChatReply> Function(ChatCancellation cancellation) request,
  }) async {
    if (state.isBusy) {
      return false;
    }

    final userMessageId = state.nextMessageId;
    final typingMessageId = userMessageId + 1;
    final cancellation = ChatCancellation();
    _activeCancellation = cancellation;
    state = state.copyWith(
      messages: <ChatMessage>[
        ...state.messages,
        ChatMessage(
          id: userMessageId,
          sender: ChatMessageSender.user,
          content: userContent,
          sticker: userSticker,
        ),
        ChatMessage.typing(id: typingMessageId),
      ],
      nextMessageId: typingMessageId + 1,
      isSending: true,
      clearError: true,
    );

    try {
      final reply = await request(cancellation);
      if (_disposed || cancellation.isCancelled) {
        return false;
      }
      final replySticker = reply.firstSticker;
      final replyText = reply.reply.trim();
      final safeSources = reply.sources
          .where((source) => source.safeUri != null)
          .toList(growable: false);
      state = state.copyWith(
        messages: _replaceMessage(
          state.messages,
          typingMessageId,
          ChatMessage(
            id: typingMessageId,
            sender: ChatMessageSender.assistant,
            content: replyText.isEmpty && replySticker == null
                ? _emptyReply
                : reply.reply,
            sticker: replySticker,
            sources: safeSources,
          ),
        ),
      );
      return true;
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) {
        return false;
      }
      final exception = _asAppException(error);
      if (exception.kind == AppExceptionKind.cancelled) {
        return false;
      }
      final message = _errorMessage(exception);
      state = state.copyWith(
        messages: _replaceMessage(
          state.messages,
          typingMessageId,
          ChatMessage(
            id: typingMessageId,
            sender: ChatMessageSender.assistant,
            content: message,
            isError: true,
          ),
        ),
        errorMessage: message,
      );
      return false;
    } finally {
      if (!_disposed) {
        _activeCancellation = null;
        state = state.copyWith(isSending: false);
      }
    }
  }

  Future<bool> clearContext() async {
    if (state.isBusy) {
      return false;
    }
    final cancellation = ChatCancellation();
    _activeCancellation = cancellation;
    state = state.copyWith(isClearing: true, clearError: true);
    try {
      await ref
          .read(chatRepositoryProvider)
          .clearContext(cancellation: cancellation);
      if (_disposed || cancellation.isCancelled) {
        return false;
      }
      state = ChatState(
        messages: <ChatMessage>[_restartGreeting(state.preferredName, 1)],
        nextMessageId: 2,
        preferredName: state.preferredName,
        chatExpanded: state.chatExpanded,
      );
      return true;
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) {
        return false;
      }
      final exception = _asAppException(error);
      if (exception.kind != AppExceptionKind.cancelled) {
        state = state.copyWith(errorMessage: _clearErrorMessage(exception));
      }
      return false;
    } finally {
      if (!_disposed) {
        _activeCancellation = null;
        state = state.copyWith(isClearing: false);
      }
    }
  }

  void toggleChatExpanded() {
    state = state.copyWith(chatExpanded: !state.chatExpanded);
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }

  static ChatMessage _greeting(String preferredName, int id) {
    final content = preferredName.isEmpty
        ? '嗨，我在呢。今天想聊点什么？'
        : '嗨，$preferredName。我在呢，今天想聊点什么？';
    return ChatMessage(
      id: id,
      sender: ChatMessageSender.assistant,
      content: content,
    );
  }

  static ChatMessage _restartGreeting(String preferredName, int id) {
    final content = preferredName.isEmpty
        ? '好啦，我们重新聊。'
        : '好啦，$preferredName。我们重新聊。';
    return ChatMessage(
      id: id,
      sender: ChatMessageSender.assistant,
      content: content,
    );
  }

  static List<ChatMessage> _replaceMessage(
    List<ChatMessage> messages,
    int messageId,
    ChatMessage replacement,
  ) {
    return messages
        .map((message) => message.id == messageId ? replacement : message)
        .toList(growable: false);
  }

  static AppException _asAppException(Object error) {
    return error is AppException
        ? error
        : const AppException(kind: AppExceptionKind.unexpected);
  }

  static String _errorMessage(AppException exception) {
    return switch (exception.kind) {
      AppExceptionKind.requestInProgress =>
        exception.detail ?? '上一条消息还在处理中，请稍后再试。',
      AppExceptionKind.rateLimited => '消息发送过于频繁，请稍后再试。',
      AppExceptionKind.unauthorized => '登录状态已失效，请重新登录。',
      AppExceptionKind.badRequest ||
      AppExceptionKind.validation => exception.detail ?? '消息内容不符合要求。',
      _ => _temporaryError,
    };
  }

  static String _clearErrorMessage(AppException exception) {
    return switch (exception.kind) {
      AppExceptionKind.unauthorized => '登录状态已失效，请重新登录。',
      AppExceptionKind.networkUnavailable => '网络不可用，未清除聊天上下文。',
      _ => '清除失败，请重试。',
    };
  }
}

final chatControllerProvider =
    NotifierProvider.autoDispose<ChatController, ChatState>(ChatController.new);
