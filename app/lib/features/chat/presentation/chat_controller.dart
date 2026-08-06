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
    this.isLoadingInitialHistory = true,
    this.isLoadingMoreHistory = false,
    this.historyInitialized = false,
    this.hasMoreHistory = false,
    this.nextBeforeId,
    this.chatExpanded = false,
    this.errorMessage,
  });

  final List<ChatMessage> messages;
  final int nextMessageId;
  final String preferredName;
  final bool isSending;
  final bool isClearing;
  final bool isLoadingInitialHistory;
  final bool isLoadingMoreHistory;
  final bool historyInitialized;
  final bool hasMoreHistory;
  final int? nextBeforeId;
  final bool chatExpanded;
  final String? errorMessage;

  bool get isBusy =>
      isSending ||
      isClearing ||
      isLoadingInitialHistory ||
      isLoadingMoreHistory;

  ChatState copyWith({
    List<ChatMessage>? messages,
    int? nextMessageId,
    String? preferredName,
    bool? isSending,
    bool? isClearing,
    bool? isLoadingInitialHistory,
    bool? isLoadingMoreHistory,
    bool? historyInitialized,
    bool? hasMoreHistory,
    int? nextBeforeId,
    bool clearNextBeforeId = false,
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
      isLoadingInitialHistory:
          isLoadingInitialHistory ?? this.isLoadingInitialHistory,
      isLoadingMoreHistory: isLoadingMoreHistory ?? this.isLoadingMoreHistory,
      historyInitialized: historyInitialized ?? this.historyInitialized,
      hasMoreHistory: hasMoreHistory ?? this.hasMoreHistory,
      nextBeforeId: clearNextBeforeId
          ? null
          : nextBeforeId ?? this.nextBeforeId,
      chatExpanded: chatExpanded ?? this.chatExpanded,
      errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
    );
  }
}

class ChatController extends Notifier<ChatState> {
  ChatCancellation? _activeCancellation;
  ChatCancellation? _historyCancellation;
  bool _disposed = false;

  @override
  ChatState build() {
    _disposed = false;
    ref.onDispose(() {
      _disposed = true;
      _activeCancellation?.cancel();
      _activeCancellation = null;
      _historyCancellation?.cancel();
      _historyCancellation = null;
    });
    final preferredName = ref.watch(chatPreferredNameProvider).trim();
    final initialState = ChatState(
      messages: <ChatMessage>[_greeting(preferredName, 1)],
      nextMessageId: 2,
      preferredName: preferredName,
    );
    Future<void>.microtask(_loadInitialHistory);
    return initialState;
  }

  Future<void> _loadInitialHistory() async {
    if (_disposed) {
      return;
    }
    final cancellation = ChatCancellation();
    _historyCancellation = cancellation;
    try {
      final page = await ref
          .read(chatRepositoryProvider)
          .loadHistory(limit: 10, cancellation: cancellation);
      if (_disposed || cancellation.isCancelled) {
        return;
      }
      final messages = page.messages.isEmpty
          ? <ChatMessage>[_greeting(state.preferredName, 1)]
          : page.messages;
      state = state.copyWith(
        messages: messages,
        nextMessageId: _nextLocalMessageId(messages),
        isLoadingInitialHistory: false,
        historyInitialized: true,
        hasMoreHistory: page.hasMore,
        nextBeforeId: page.nextBeforeId,
        clearNextBeforeId: page.nextBeforeId == null,
        clearError: true,
      );
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) {
        return;
      }
      state = state.copyWith(
        isLoadingInitialHistory: false,
        historyInitialized: true,
        hasMoreHistory: false,
        clearNextBeforeId: true,
        errorMessage: _historyErrorMessage(_asAppException(error)),
      );
    } finally {
      if (identical(_historyCancellation, cancellation)) {
        _historyCancellation = null;
      }
    }
  }

  Future<bool> loadOlderMessages() async {
    if (state.isBusy || !state.historyInitialized || !state.hasMoreHistory) {
      return false;
    }
    final beforeId = state.nextBeforeId;
    if (beforeId == null) {
      return false;
    }

    final cancellation = ChatCancellation();
    _historyCancellation = cancellation;
    state = state.copyWith(isLoadingMoreHistory: true, clearError: true);
    try {
      final page = await ref
          .read(chatRepositoryProvider)
          .loadHistory(
            beforeId: beforeId,
            limit: 10,
            cancellation: cancellation,
          );
      if (_disposed || cancellation.isCancelled) {
        return false;
      }
      final existingIds = state.messages.map((message) => message.id).toSet();
      final olderMessages = page.messages
          .where((message) => !existingIds.contains(message.id))
          .toList(growable: false);
      state = state.copyWith(
        messages: <ChatMessage>[...olderMessages, ...state.messages],
        isLoadingMoreHistory: false,
        hasMoreHistory: page.hasMore,
        nextBeforeId: page.nextBeforeId,
        clearNextBeforeId: page.nextBeforeId == null,
      );
      return olderMessages.isNotEmpty;
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) {
        return false;
      }
      state = state.copyWith(
        isLoadingMoreHistory: false,
        errorMessage: _historyErrorMessage(_asAppException(error)),
      );
      return false;
    } finally {
      if (!_disposed && state.isLoadingMoreHistory) {
        state = state.copyWith(isLoadingMoreHistory: false);
      }
      if (identical(_historyCancellation, cancellation)) {
        _historyCancellation = null;
      }
    }
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
        isLoadingInitialHistory: false,
        historyInitialized: true,
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

  static int _nextLocalMessageId(List<ChatMessage> messages) {
    var maximumId = 0;
    for (final message in messages) {
      if (message.id > maximumId) {
        maximumId = message.id;
      }
    }
    return maximumId + 1;
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

  static String _historyErrorMessage(AppException exception) {
    return switch (exception.kind) {
      AppExceptionKind.unauthorized => '登录状态已失效，请重新登录。',
      AppExceptionKind.networkUnavailable => '网络不可用，暂时没有加载聊天记录。',
      _ => '聊天记录加载失败，可以稍后重试。',
    };
  }
}

final chatControllerProvider =
    NotifierProvider.autoDispose<ChatController, ChatState>(ChatController.new);
