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
    expect(repository.sendCalls, 0);
  });

  test(
    'inserts user and typing immediately and blocks concurrent sends',
    () async {
      final gate = Completer<ChatReply>();
      final repository = FakeChatRepository(onSend: (_, _) => gate.future);
      final container = _container(repository);
      addTearDown(container.dispose);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);
      final controller = container.read(chatControllerProvider.notifier);

      final first = controller.sendMessage('  第一条  ');
      final sendingState = container.read(chatControllerProvider);
      expect(sendingState.isSending, isTrue);
      expect(
        sendingState.messages.map((message) => message.content),
        contains('第一条'),
      );
      expect(sendingState.messages.last.isTyping, isTrue);

      final secondAccepted = await controller.sendMessage('第二条');
      expect(secondAccepted, isFalse);
      expect(repository.sendCalls, 1);

      gate.complete(const ChatReply(reply: '收到第一条'));
      expect(await first, isTrue);
      final completedState = container.read(chatControllerProvider);
      expect(completedState.isSending, isFalse);
      expect(completedState.messages.last.isTyping, isFalse);
      expect(completedState.messages.last.content, '收到第一条');
    },
  );

  test(
    'uses first sticker and filters unsafe sources from a successful reply',
    () async {
      final repository = FakeChatRepository(
        onSend: (_, _) async => const ChatReply(
          reply: '看看这个',
          contentParts: <ChatContentPart>[
            ChatContentPart(type: ChatContentPartType.text, text: '看看这个'),
            ChatContentPart(
              type: ChatContentPartType.sticker,
              stickerId: 'happy',
              url: 'https://cdn.example.test/happy.png',
            ),
          ],
          sources: <ChatSource>[
            ChatSource(title: 'safe', url: 'https://example.test/source'),
            ChatSource(title: 'unsafe', url: 'javascript:alert(1)'),
          ],
        ),
      );
      final container = _container(repository);
      addTearDown(container.dispose);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);

      final accepted = await container
          .read(chatControllerProvider.notifier)
          .sendMessage('来源');
      final message = container.read(chatControllerProvider).messages.last;

      expect(accepted, isTrue);
      expect(message.sticker?.stickerId, 'happy');
      expect(message.sources.map((source) => source.title), <String>['safe']);
    },
  );

  test(
    'sends a sticker as a standalone user message and waits for Echo',
    () async {
      const sticker = ChatSticker(
        stickerId: 'wave',
        url: 'https://cdn.example.test/wave.png',
      );
      final repository = FakeChatRepository(
        onSendSticker: (sentSticker, _) async {
          expect(sentSticker.stickerId, 'wave');
          return const ChatReply(reply: '我看到你在挥手啦。');
        },
      );
      final container = _container(repository);
      addTearDown(container.dispose);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);

      final accepted = await container
          .read(chatControllerProvider.notifier)
          .sendSticker(sticker);
      final messages = container.read(chatControllerProvider).messages;

      expect(accepted, isTrue);
      expect(repository.sendStickerCalls, 1);
      expect(messages[messages.length - 2].sender, ChatMessageSender.user);
      expect(messages[messages.length - 2].content, isEmpty);
      expect(messages[messages.length - 2].sticker?.stickerId, 'wave');
      expect(messages.last.content, '我看到你在挥手啦。');
    },
  );

  test('clear resets memory messages and creates a restart greeting', () async {
    final repository = FakeChatRepository();
    final container = _container(repository, preferredName: '小叶');
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
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

  test('maps 409 to a stable error and replaces typing placeholder', () async {
    final repository = FakeChatRepository(
      onSend: (_, _) async => throw const AppException(
        kind: AppExceptionKind.requestInProgress,
        httpStatus: 409,
      ),
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);

    final accepted = await container
        .read(chatControllerProvider.notifier)
        .sendMessage('再发一条');
    final state = container.read(chatControllerProvider);

    expect(accepted, isFalse);
    expect(state.messages.last.isTyping, isFalse);
    expect(state.messages.last.isError, isTrue);
    expect(state.errorMessage, '上一条消息还在处理中，请稍后再试。');
  });

  test('disposing the page provider cancels the in-flight request', () async {
    final cancelled = Completer<void>();
    final request = Completer<ChatReply>();
    final repository = FakeChatRepository(
      onSend: (_, cancellation) {
        cancellation!.whenCancelled(() {
          if (!cancelled.isCompleted) {
            cancelled.complete();
          }
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
    final send = container
        .read(chatControllerProvider.notifier)
        .sendMessage('离开页面');

    subscription.close();
    await container.pump();
    await cancelled.future;
    expect(repository.lastCancellation?.isCancelled, isTrue);
    expect(await send, isFalse);
    container.dispose();
  });
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
