import 'dart:async';

import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/chat/data/chat_providers.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

const _temporaryError = '（我刚才有点卡住了，等一下再和我说一次好吗？）';
const _turnFailedMessage = 'Echo 刚才没有回复，你可以继续说。';

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
    required this.nextLocalMessageId,
    required this.preferredName,
    this.conversationId = '',
    this.echoTyping = false,
    this.eventConnected = false,
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
  final int nextLocalMessageId;
  final String preferredName;
  final String conversationId;
  final bool echoTyping;
  final bool eventConnected;
  final bool isClearing;
  final bool isLoadingInitialHistory;
  final bool isLoadingMoreHistory;
  final bool historyInitialized;
  final bool hasMoreHistory;
  final int? nextBeforeId;
  final bool chatExpanded;
  final String? errorMessage;

  bool get isBusy => isClearing || isLoadingInitialHistory;
  bool get canCompose => historyInitialized && !isClearing;
  bool get isSending =>
      messages.any((message) => message.sendState == ChatSendState.sending);
  int get nextMessageId {
    var maximum = 0;
    for (final message in messages) {
      if (message.id > maximum) maximum = message.id;
    }
    return maximum + 1;
  }

  ChatState copyWith({
    List<ChatMessage>? messages,
    int? nextLocalMessageId,
    String? preferredName,
    String? conversationId,
    bool? echoTyping,
    bool? eventConnected,
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
      nextLocalMessageId: nextLocalMessageId ?? this.nextLocalMessageId,
      preferredName: preferredName ?? this.preferredName,
      conversationId: conversationId ?? this.conversationId,
      echoTyping: echoTyping ?? this.echoTyping,
      eventConnected: eventConnected ?? this.eventConnected,
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
  static const _reconnectDelays = <Duration>[
    Duration(seconds: 1),
    Duration(seconds: 2),
    Duration(seconds: 5),
    Duration(seconds: 10),
    Duration(seconds: 30),
  ];

  final _uuid = const Uuid();
  final Map<String, ChatCancellation> _sendCancellations =
      <String, ChatCancellation>{};
  ChatCancellation? _historyCancellation;
  ChatCancellation? _eventCancellation;
  StreamSubscription<ChatEvent>? _eventSubscription;
  Timer? _reconnectTimer;
  Future<void> _revealChain = Future<void>.value();
  bool _disposed = false;
  bool _serverTyping = false;
  int _activeRevealGroups = 0;
  int _reconnectAttempt = 0;
  int _revealGeneration = 0;

  @override
  ChatState build() {
    _disposed = false;
    ref.onDispose(_dispose);
    final preferredName = ref.watch(chatPreferredNameProvider).trim();
    final initialState = ChatState(
      messages: <ChatMessage>[_greeting(preferredName)],
      nextLocalMessageId: -1,
      preferredName: preferredName,
    );
    Future<void>.microtask(_loadInitialHistory);
    return initialState;
  }

  Future<void> _loadInitialHistory() async {
    if (_disposed) return;
    final cancellation = ChatCancellation();
    _historyCancellation?.cancel();
    _historyCancellation = cancellation;
    try {
      final page = await ref
          .read(chatRepositoryProvider)
          .loadHistory(limit: 10, cancellation: cancellation);
      if (_disposed || cancellation.isCancelled) return;
      final messages = page.messages.isEmpty
          ? <ChatMessage>[_greeting(state.preferredName)]
          : page.messages;
      state = state.copyWith(
        messages: messages,
        conversationId: page.conversationId,
        isLoadingInitialHistory: false,
        historyInitialized: true,
        hasMoreHistory: page.hasMore,
        nextBeforeId: page.nextBeforeId,
        clearNextBeforeId: page.nextBeforeId == null,
        clearError: true,
      );
      unawaited(_connectEvents(_latestServerMessageId(messages)));
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) return;
      state = state.copyWith(
        isLoadingInitialHistory: false,
        historyInitialized: true,
        hasMoreHistory: false,
        clearNextBeforeId: true,
        errorMessage: _historyErrorMessage(_asAppException(error)),
      );
      unawaited(_connectEvents(_latestServerMessageId(state.messages)));
    } finally {
      if (identical(_historyCancellation, cancellation)) {
        _historyCancellation = null;
      }
    }
  }

  Future<bool> loadOlderMessages() async {
    if (_disposed ||
        state.isClearing ||
        state.isLoadingInitialHistory ||
        state.isLoadingMoreHistory ||
        !state.historyInitialized ||
        !state.hasMoreHistory) {
      return false;
    }
    final beforeId = state.nextBeforeId;
    if (beforeId == null) return false;

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
      if (_disposed || cancellation.isCancelled) return false;
      final existingIds = state.messages
          .where((message) => message.id > 0)
          .map((message) => message.id)
          .toSet();
      final older = page.messages
          .where((message) => !existingIds.contains(message.id))
          .toList(growable: false);
      state = state.copyWith(
        messages: <ChatMessage>[...older, ...state.messages],
        isLoadingMoreHistory: false,
        hasMoreHistory: page.hasMore,
        nextBeforeId: page.nextBeforeId,
        clearNextBeforeId: page.nextBeforeId == null,
      );
      return older.isNotEmpty;
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) return false;
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
    final message = rawMessage.trim();
    if (!state.canCompose || message.isEmpty || message.length > 2000) {
      return false;
    }
    final clientMessageId = _uuid.v4();
    final local = ChatMessage(
      id: state.nextLocalMessageId,
      sender: ChatMessageSender.user,
      content: message,
      clientMessageId: clientMessageId,
      sendState: ChatSendState.sending,
      createdAt: DateTime.now(),
    );
    _appendLocalMessage(local);
    return _acceptLocalMessage(local);
  }

  Future<bool> sendSticker(ChatSticker sticker) async {
    if (!state.canCompose ||
        sticker.stickerId.isEmpty ||
        sticker.safeUri == null) {
      return false;
    }
    final clientMessageId = _uuid.v4();
    final local = ChatMessage(
      id: state.nextLocalMessageId,
      sender: ChatMessageSender.user,
      content: '',
      sticker: sticker,
      clientMessageId: clientMessageId,
      sendState: ChatSendState.sending,
      createdAt: DateTime.now(),
    );
    _appendLocalMessage(local);
    return _acceptLocalMessage(local);
  }

  Future<bool> retryMessage(String clientMessageId) async {
    final index = state.messages.indexWhere(
      (message) =>
          message.clientMessageId == clientMessageId &&
          message.sender == ChatMessageSender.user,
    );
    if (index < 0 || !state.canCompose) return false;
    final message = state.messages[index];
    if (message.sendState != ChatSendState.failed) return false;
    final messages = List<ChatMessage>.of(state.messages);
    final retrying = message.copyWith(sendState: ChatSendState.sending);
    messages[index] = retrying;
    state = state.copyWith(messages: messages, clearError: true);
    return _acceptLocalMessage(retrying);
  }

  void _appendLocalMessage(ChatMessage message) {
    final withoutGreeting =
        state.messages.length == 1 && state.messages.single.id == 0
        ? const <ChatMessage>[]
        : state.messages;
    state = state.copyWith(
      messages: <ChatMessage>[...withoutGreeting, message],
      nextLocalMessageId: state.nextLocalMessageId - 1,
      clearError: true,
    );
  }

  Future<bool> _acceptLocalMessage(ChatMessage local) async {
    final cancellation = ChatCancellation();
    _sendCancellations[local.clientMessageId] = cancellation;
    try {
      final repository = ref.read(chatRepositoryProvider);
      final acceptance = local.sticker == null
          ? await repository.acceptTextMessage(
              local.content,
              local.clientMessageId,
              cancellation: cancellation,
            )
          : await repository.acceptStickerMessage(
              local.sticker!,
              clientMessageId: local.clientMessageId,
              cancellation: cancellation,
            );
      if (_disposed || cancellation.isCancelled) return false;
      _mergeServerMessages(<ChatMessage>[acceptance.message]);
      if (acceptance.conversationId.isNotEmpty &&
          acceptance.conversationId != state.conversationId) {
        state = state.copyWith(conversationId: acceptance.conversationId);
      }
      return true;
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) return false;
      final exception = _asAppException(error);
      if (exception.kind == AppExceptionKind.cancelled) return false;
      _markMessageFailed(local.clientMessageId);
      state = state.copyWith(errorMessage: _sendErrorMessage(exception));
      return false;
    } finally {
      _sendCancellations.remove(local.clientMessageId);
    }
  }

  void _markMessageFailed(String clientMessageId) {
    state = state.copyWith(
      messages: state.messages
          .map(
            (message) => message.clientMessageId == clientMessageId
                ? message.copyWith(sendState: ChatSendState.failed)
                : message,
          )
          .toList(growable: false),
    );
  }

  Future<void> _connectEvents(int afterMessageId) async {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _eventCancellation?.cancel();
    final previousSubscription = _eventSubscription;
    if (previousSubscription != null) {
      await previousSubscription.cancel();
    }
    if (_disposed) return;
    final cancellation = ChatCancellation();
    _eventCancellation = cancellation;
    _eventSubscription = ref
        .read(chatRepositoryProvider)
        .watchEvents(afterMessageId: afterMessageId, cancellation: cancellation)
        .listen(
          _handleEvent,
          onError: (Object error, StackTrace stackTrace) {
            if (_disposed || cancellation.isCancelled) return;
            state = state.copyWith(eventConnected: false);
            _scheduleReconnect();
          },
          onDone: () {
            if (_disposed || cancellation.isCancelled) return;
            state = state.copyWith(eventConnected: false);
            _scheduleReconnect();
          },
        );
  }

  void _scheduleReconnect() {
    if (_disposed || _reconnectTimer?.isActive == true) return;
    final index = _reconnectAttempt.clamp(0, _reconnectDelays.length - 1);
    final delay = _reconnectDelays[index];
    _reconnectAttempt += 1;
    _reconnectTimer = Timer(
      delay,
      () => unawaited(_connectEvents(_latestServerMessageId(state.messages))),
    );
  }

  void _handleEvent(ChatEvent event) {
    if (_disposed) return;
    switch (event.type) {
      case ChatEventType.ready:
        _reconnectAttempt = 0;
        _serverTyping = event.echoTyping;
        state = state.copyWith(
          eventConnected: true,
          conversationId: event.conversationId.isEmpty
              ? state.conversationId
              : event.conversationId,
          echoTyping: _serverTyping || _activeRevealGroups > 0,
        );
      case ChatEventType.sync:
        _mergeServerMessages(event.messages);
      case ChatEventType.typingStarted:
        _serverTyping = true;
        state = state.copyWith(echoTyping: true);
      case ChatEventType.typingStopped:
        _serverTyping = false;
        state = state.copyWith(echoTyping: _activeRevealGroups > 0);
      case ChatEventType.delivery:
        _enqueueDelivery(event);
      case ChatEventType.turnFailed:
        _serverTyping = false;
        state = state.copyWith(
          echoTyping: _activeRevealGroups > 0,
          errorMessage: _turnFailedMessage,
        );
      case ChatEventType.conversationReset:
        _serverTyping = false;
        _cancelRevealQueue();
        unawaited(_loadInitialHistory());
      case ChatEventType.heartbeat:
        break;
    }
  }

  void _enqueueDelivery(ChatEvent event) {
    final generation = _revealGeneration;
    _activeRevealGroups += 1;
    state = state.copyWith(echoTyping: true);
    _revealChain = _revealChain
        .catchError((Object _) {})
        .then((_) => _revealDelivery(event, generation));
  }

  Future<void> _revealDelivery(ChatEvent event, int generation) async {
    try {
      final skipDelay = event.messages.any(
        (message) =>
            message.createdAt != null &&
            DateTime.now().difference(message.createdAt!).abs() >
                const Duration(seconds: 10),
      );
      for (var index = 0; index < event.messages.length; index += 1) {
        if (_disposed || generation != _revealGeneration) return;
        final rawDelay = index < event.presentation.messageDelaysMs.length
            ? event.presentation.messageDelaysMs[index]
            : 0;
        final delay = skipDelay ? 0 : rawDelay.clamp(0, 2500);
        if (delay > 0) {
          await Future<void>.delayed(Duration(milliseconds: delay));
        }
        if (_disposed || generation != _revealGeneration) return;
        _mergeServerMessages(<ChatMessage>[event.messages[index]]);
      }
    } finally {
      _activeRevealGroups = (_activeRevealGroups - 1).clamp(0, 1 << 20);
      if (!_disposed && generation == _revealGeneration) {
        state = state.copyWith(
          echoTyping: _serverTyping || _activeRevealGroups > 0,
        );
      }
    }
  }

  void _mergeServerMessages(List<ChatMessage> incoming) {
    if (_disposed || incoming.isEmpty) return;
    final messages = List<ChatMessage>.of(state.messages);
    if (messages.length == 1 && messages.single.id == 0) {
      messages.clear();
    }
    for (final message in incoming) {
      final index = messages.indexWhere(
        (existing) =>
            (message.clientMessageId.isNotEmpty &&
                existing.clientMessageId == message.clientMessageId) ||
            (message.id > 0 && existing.id == message.id),
      );
      if (index >= 0) {
        messages[index] = message;
      } else {
        messages.add(message);
      }
    }
    messages.sort(_compareMessages);
    state = state.copyWith(messages: messages);
  }

  int _compareMessages(ChatMessage left, ChatMessage right) {
    final leftTime = left.createdAt;
    final rightTime = right.createdAt;
    if (leftTime != null && rightTime != null) {
      final compared = leftTime.compareTo(rightTime);
      if (compared != 0) return compared;
    }
    if (left.id > 0 && right.id > 0) return left.id.compareTo(right.id);
    if (left.id == right.id) return 0;
    return left.id < right.id ? 1 : -1;
  }

  Future<bool> clearContext() async {
    if (state.isClearing) return false;
    _cancelRevealQueue();
    for (final cancellation in _sendCancellations.values) {
      cancellation.cancel();
    }
    _sendCancellations.clear();
    state = state.copyWith(isClearing: true, clearError: true);
    final cancellation = ChatCancellation();
    try {
      await ref
          .read(chatRepositoryProvider)
          .clearContext(cancellation: cancellation);
      if (_disposed || cancellation.isCancelled) return false;
      _serverTyping = false;
      state = ChatState(
        messages: <ChatMessage>[_restartGreeting(state.preferredName)],
        nextLocalMessageId: -1,
        preferredName: state.preferredName,
        conversationId: state.conversationId,
        isLoadingInitialHistory: false,
        historyInitialized: true,
        chatExpanded: state.chatExpanded,
      );
      unawaited(_connectEvents(0));
      return true;
    } on Object catch (error) {
      if (_disposed || cancellation.isCancelled) return false;
      state = state.copyWith(
        isClearing: false,
        errorMessage: _clearErrorMessage(_asAppException(error)),
      );
      return false;
    } finally {
      if (!_disposed && state.isClearing) {
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

  void _cancelRevealQueue() {
    _revealGeneration += 1;
    _activeRevealGroups = 0;
    _revealChain = Future<void>.value();
  }

  void _dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _historyCancellation?.cancel();
    _eventCancellation?.cancel();
    unawaited(_eventSubscription?.cancel());
    for (final cancellation in _sendCancellations.values) {
      cancellation.cancel();
    }
    _sendCancellations.clear();
    _cancelRevealQueue();
  }

  static int _latestServerMessageId(List<ChatMessage> messages) {
    var maximum = 0;
    for (final message in messages) {
      if (message.id > maximum) maximum = message.id;
    }
    return maximum;
  }

  static ChatMessage _greeting(String preferredName) {
    final content = preferredName.isEmpty
        ? '嗨，我在呢。今天想聊点什么？'
        : '嗨，$preferredName。我在呢，今天想聊点什么？';
    return ChatMessage(
      id: 0,
      sender: ChatMessageSender.assistant,
      content: content,
    );
  }

  static ChatMessage _restartGreeting(String preferredName) {
    final content = preferredName.isEmpty
        ? '好啦，我们重新聊。'
        : '好啦，$preferredName。我们重新聊。';
    return ChatMessage(
      id: 0,
      sender: ChatMessageSender.assistant,
      content: content,
    );
  }

  static AppException _asAppException(Object error) {
    return error is AppException
        ? error
        : const AppException(kind: AppExceptionKind.unexpected);
  }

  static String _sendErrorMessage(AppException exception) {
    return switch (exception.kind) {
      AppExceptionKind.rateLimited => '待处理消息较多，请稍后再发。',
      AppExceptionKind.unauthorized => '登录状态已失效，请重新登录。',
      AppExceptionKind.badRequest ||
      AppExceptionKind.validation => exception.detail ?? '消息内容不符合要求。',
      AppExceptionKind.networkUnavailable => '网络不可用，点击失败消息可以重试。',
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
