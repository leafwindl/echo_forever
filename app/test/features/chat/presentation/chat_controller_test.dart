import 'dart:async';

import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/chat/data/chat_providers.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/presentation/chat_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes.dart';

void main() {
  test('creates one local preferred-name greeting on first entry', () {
    final repository = FakeChatRepository();
    final container = _container(repository, preferredName: '小叶');
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);

    final state = container.read(chatControllerProvider);

    expect(state.messages, hasLength(1));
    expect(state.messages.single.sender, ChatMessageSender.assistant);
    expect(state.messages.single.content, '嗨，小叶。我在呢，今天想聊点什么？');
    expect(repository.acceptTextCalls, 0);
  });

  test(
    'accepts a second message while the first ACK is still pending',
    () async {
      final firstAck = Completer<ChatMessageAcceptance>();
      var calls = 0;
      final repository = FakeChatRepository(
        onAcceptText: (message, clientMessageId, _) {
          calls += 1;
          if (calls == 1) return firstAck.future;
          return Future<ChatMessageAcceptance>.value(
            _acceptance(2, clientMessageId, message),
          );
        },
      );
      final container = _container(repository);
      addTearDown(container.dispose);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);
      await _initializeHistory(container);
      final controller = container.read(chatControllerProvider.notifier);

      final first = controller.sendMessage('第一条');
      final firstLocal = container.read(chatControllerProvider).messages.single;
      expect(firstLocal.content, '第一条');
      expect(firstLocal.sendState, ChatSendState.sending);

      final second = await controller.sendMessage('第二条');
      expect(second, isTrue);
      expect(repository.acceptTextCalls, 2);
      expect(
        container
            .read(chatControllerProvider)
            .messages
            .map((item) => item.content),
        containsAll(<String>['第一条', '第二条']),
      );

      firstAck.complete(_acceptance(1, firstLocal.clientMessageId, '第一条'));
      expect(await first, isTrue);
      expect(
        container
            .read(chatControllerProvider)
            .messages
            .where((message) => message.sender == ChatMessageSender.user)
            .every((message) => message.sendState == ChatSendState.sent),
        isTrue,
      );
    },
  );

  test('receives typing and a multi-message delivery independently', () async {
    final repository = FakeChatRepository();
    final container = _container(repository);
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await _initializeHistory(container);

    repository.emit(
      const ChatEvent(type: ChatEventType.typingStarted, turnId: 'turn-1'),
    );
    await container.pump();
    expect(container.read(chatControllerProvider).echoTyping, isTrue);

    repository.emit(
      ChatEvent(
        type: ChatEventType.delivery,
        messages: <ChatMessage>[
          ChatMessage(
            id: 10,
            sender: ChatMessageSender.assistant,
            content: '我在呀。',
            replyGroupId: 'reply-1',
            sequenceInGroup: 0,
            createdAt: DateTime.now(),
          ),
          ChatMessage(
            id: 11,
            sender: ChatMessageSender.assistant,
            content: '今天发生什么了？',
            replyGroupId: 'reply-1',
            sequenceInGroup: 1,
            createdAt: DateTime.now().add(const Duration(milliseconds: 1)),
          ),
          ChatMessage(
            id: 12,
            sender: ChatMessageSender.assistant,
            content: '',
            sticker: const ChatSticker(
              stickerId: 'wave',
              url: 'https://cdn.example.test/wave.png',
            ),
            replyGroupId: 'reply-1',
            sequenceInGroup: 2,
            createdAt: DateTime.now().add(const Duration(milliseconds: 2)),
          ),
        ],
        presentation: const ChatDeliveryPresentation(
          messageDelaysMs: <int>[0, 0, 0],
        ),
      ),
    );
    repository.emit(
      const ChatEvent(type: ChatEventType.typingStopped, turnId: 'turn-1'),
    );
    await _pumpAsync(container);

    final state = container.read(chatControllerProvider);
    expect(state.messages.map((message) => message.content), <String>[
      '我在呀。',
      '今天发生什么了？',
      '',
    ]);
    expect(state.messages.last.sticker?.stickerId, 'wave');
    expect(state.echoTyping, isFalse);
  });

  test('keeps typing visible for the length-based reveal delay', () async {
    final repository = FakeChatRepository();
    final container = _container(repository);
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await _initializeHistory(container);

    repository.emit(
      ChatEvent(
        type: ChatEventType.delivery,
        messages: <ChatMessage>[
          ChatMessage(
            id: 9,
            sender: ChatMessageSender.assistant,
            content: '稍长一点的回复',
            createdAt: DateTime.now(),
          ),
        ],
        presentation: const ChatDeliveryPresentation(
          messageDelaysMs: <int>[60],
        ),
      ),
    );
    await container.pump();
    expect(container.read(chatControllerProvider).echoTyping, isTrue);
    expect(
      container.read(chatControllerProvider).messages,
      isNot(contains(predicate<ChatMessage>((item) => item.id == 9))),
    );

    await Future<void>.delayed(const Duration(milliseconds: 80));
    await container.pump();
    expect(
      container.read(chatControllerProvider).messages.map((item) => item.id),
      contains(9),
    );
    expect(container.read(chatControllerProvider).echoTyping, isFalse);
  });

  test('sends a sticker as a standalone accepted user message', () async {
    const sticker = ChatSticker(
      stickerId: 'wave',
      url: 'https://cdn.example.test/wave.png',
    );
    final repository = FakeChatRepository();
    final container = _container(repository);
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await _initializeHistory(container);

    final accepted = await container
        .read(chatControllerProvider.notifier)
        .sendSticker(sticker);
    final message = container.read(chatControllerProvider).messages.single;

    expect(accepted, isTrue);
    expect(repository.acceptStickerCalls, 1);
    expect(message.sender, ChatMessageSender.user);
    expect(message.content, isEmpty);
    expect(message.sticker?.stickerId, 'wave');
    expect(message.sendState, ChatSendState.sent);
  });

  test('failed message retries with the same client message id', () async {
    var attempts = 0;
    final repository = FakeChatRepository(
      onAcceptText: (message, clientMessageId, _) async {
        attempts += 1;
        if (attempts == 1) {
          throw const AppException(kind: AppExceptionKind.networkUnavailable);
        }
        return _acceptance(5, clientMessageId, message);
      },
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await _initializeHistory(container);
    final controller = container.read(chatControllerProvider.notifier);

    expect(await controller.sendMessage('重试这条'), isFalse);
    final failed = container.read(chatControllerProvider).messages.single;
    expect(failed.sendState, ChatSendState.failed);

    expect(await controller.retryMessage(failed.clientMessageId), isTrue);
    final sent = container.read(chatControllerProvider).messages.single;
    expect(sent.sendState, ChatSendState.sent);
    expect(repository.clientMessageIds, <String>[
      failed.clientMessageId,
      failed.clientMessageId,
    ]);
  });

  test('duplicate sync and delivery messages are de-duplicated', () async {
    final repository = FakeChatRepository();
    final container = _container(repository);
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await _initializeHistory(container);
    final message = ChatMessage(
      id: 44,
      sender: ChatMessageSender.assistant,
      content: '只显示一次',
      createdAt: DateTime.now(),
    );

    repository.emit(
      ChatEvent(type: ChatEventType.sync, messages: <ChatMessage>[message]),
    );
    repository.emit(
      ChatEvent(
        type: ChatEventType.delivery,
        messages: <ChatMessage>[message],
        presentation: const ChatDeliveryPresentation(messageDelaysMs: <int>[0]),
      ),
    );
    await _pumpAsync(container);

    expect(
      container
          .read(chatControllerProvider)
          .messages
          .where((item) => item.id == 44),
      hasLength(1),
    );
  });

  test('clear resets messages and creates a restart greeting', () async {
    final repository = FakeChatRepository();
    final container = _container(repository, preferredName: '小叶');
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await _initializeHistory(container);
    final controller = container.read(chatControllerProvider.notifier);
    await controller.sendMessage('旧消息');
    controller.toggleChatExpanded();

    final cleared = await controller.clearContext();
    final state = container.read(chatControllerProvider);

    expect(cleared, isTrue);
    expect(repository.clearCalls, 1);
    expect(state.messages, hasLength(1));
    expect(state.messages.single.content, '好啦，小叶。我们重新聊。');
    expect(state.chatExpanded, isTrue);
  });

  test('disposing cancels only the pending ACK connection', () async {
    final cancelled = Completer<void>();
    final request = Completer<ChatMessageAcceptance>();
    final repository = FakeChatRepository(
      onAcceptText: (message, clientMessageId, cancellation) {
        cancellation!.whenCancelled(() {
          if (!cancelled.isCompleted) cancelled.complete();
          if (!request.isCompleted) {
            request.completeError(
              const AppException(kind: AppExceptionKind.cancelled),
            );
          }
        });
        return request.future;
      },
    );
    final container = _container(repository);
    final subscription = _keepAlive(container);
    await _initializeHistory(container);
    final send = container
        .read(chatControllerProvider.notifier)
        .sendMessage('离开页面');

    subscription.close();
    await container.pump();
    await cancelled.future;
    expect(await send, isFalse);
    container.dispose();
  });

  test('restores history and prepends an older page', () async {
    final repository = FakeChatRepository(
      onLoadHistory: (beforeId, _, _, _) async {
        if (beforeId == null) {
          return const ChatHistoryPage(
            conversationId: 'conv-history',
            messages: <ChatMessage>[
              ChatMessage(
                id: 11,
                sender: ChatMessageSender.user,
                content: '较新的消息',
              ),
              ChatMessage(
                id: 12,
                sender: ChatMessageSender.assistant,
                content: '较新的回复',
              ),
            ],
            hasMore: true,
            nextBeforeId: 11,
          );
        }
        return const ChatHistoryPage(
          conversationId: 'conv-history',
          messages: <ChatMessage>[
            ChatMessage(
              id: 1,
              sender: ChatMessageSender.user,
              content: '最早的消息',
            ),
            ChatMessage(
              id: 2,
              sender: ChatMessageSender.assistant,
              content: '最早的回复',
            ),
          ],
          hasMore: false,
        );
      },
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await _initializeHistory(container);

    expect(
      await container.read(chatControllerProvider.notifier).loadOlderMessages(),
      isTrue,
    );
    final state = container.read(chatControllerProvider);
    expect(state.messages.map((message) => message.id), <int>[1, 2, 11, 12]);
    expect(repository.historyBeforeIds, <int?>[null, 11]);
  });
}

ChatMessageAcceptance _acceptance(
  int id,
  String clientMessageId,
  String content,
) {
  return ChatMessageAcceptance(
    conversationId: 'conv-fake',
    message: ChatMessage(
      id: id,
      sender: ChatMessageSender.user,
      content: content,
      clientMessageId: clientMessageId,
      createdAt: DateTime.now(),
    ),
    turn: const ChatAcceptedTurn(turnId: 'turn-fake', status: 'collecting'),
  );
}

ProviderContainer _container(
  FakeChatRepository repository, {
  String preferredName = '',
}) {
  return ProviderContainer(
    overrides: [
      chatRepositoryProvider.overrideWithValue(repository),
      chatPreferredNameProvider.overrideWithValue(preferredName),
    ],
  );
}

ProviderSubscription<ChatState> _keepAlive(ProviderContainer container) {
  return container.listen<ChatState>(
    chatControllerProvider,
    (_, _) {},
    fireImmediately: true,
  );
}

Future<void> _initializeHistory(ProviderContainer container) async {
  await container.pump();
  await container.pump();
}

Future<void> _pumpAsync(ProviderContainer container) async {
  await container.pump();
  await Future<void>.delayed(Duration.zero);
  await container.pump();
}
