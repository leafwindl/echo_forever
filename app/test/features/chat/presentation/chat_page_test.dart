import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/app_update/presentation/app_update_controller.dart';
import 'package:echo_app/features/chat/data/chat_providers.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/presentation/chat_controller.dart';
import 'package:echo_app/features/chat/presentation/chat_page.dart';
import 'package:echo_app/features/letters/presentation/letters_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../../stickers/fakes.dart' as sticker_fakes;
import '../fakes.dart';

void main() {
  testWidgets('shows the local greeting and idle character artwork', (
    tester,
  ) async {
    await _pumpChat(tester, FakeChatRepository(), preferredName: '小叶');

    expect(find.text('嗨，小叶。我在呢，今天想聊点什么？'), findsOneWidget);
    expect(find.byKey(const Key('static-character-renderer')), findsOneWidget);
    expect(find.byKey(const Key('character-idle-image')), findsOneWidget);
    expect(find.byKey(const Key('chat-input')), findsOneWidget);
    expect(find.byKey(const Key('open-call-button')), findsNothing);
  });

  testWidgets('shows the unread letter badge in the chat toolbar', (
    tester,
  ) async {
    await _pumpChat(tester, FakeChatRepository(), unreadLetterCount: 3);

    expect(find.byKey(const Key('open-letters-button')), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });

  testWidgets('shows only the public app version beside the title', (
    tester,
  ) async {
    await _pumpChat(
      tester,
      FakeChatRepository(),
      installedAppVersion: '1.0.5+10',
    );

    expect(find.byKey(const Key('app-version-badge')), findsOneWidget);
    expect(find.text('v1.0.5'), findsOneWidget);
    expect(find.textContaining('+10'), findsNothing);
  });

  testWidgets('restores recent chat and accepts an older page', (tester) async {
    final repository = FakeChatRepository(
      onLoadHistory: (beforeId, _, _, _) async {
        if (beforeId == null) {
          return const ChatHistoryPage(
            conversationId: 'conv-history',
            messages: <ChatMessage>[
              ChatMessage(
                id: 11,
                sender: ChatMessageSender.user,
                content: '最近的消息',
              ),
              ChatMessage(
                id: 12,
                sender: ChatMessageSender.assistant,
                content: '最近的回复',
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
              content: '更早的消息',
            ),
          ],
          hasMore: false,
        );
      },
    );
    await _pumpChat(tester, repository);

    expect(find.text('嗨，我在呢。今天想聊点什么？'), findsNothing);
    expect(find.text('最近的消息'), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(ChatPage)),
    );
    await container.read(chatControllerProvider.notifier).loadOlderMessages();
    await tester.pumpAndSettle();

    expect(
      container
          .read(chatControllerProvider)
          .messages
          .map((message) => message.content),
      contains('更早的消息'),
    );
    expect(repository.historyBeforeIds, <int?>[null, 11]);
  });

  testWidgets('keeps input and stickers enabled while Echo is typing', (
    tester,
  ) async {
    final repository = FakeChatRepository();
    await _pumpChat(tester, repository);

    await tester.enterText(find.byKey(const Key('chat-input')), '第一条');
    await tester.pump();
    await tester.tap(find.byKey(const Key('chat-send-button')));
    await tester.pump();
    repository.emit(
      const ChatEvent(type: ChatEventType.typingStarted, turnId: 'turn-1'),
    );
    await tester.pump();

    expect(find.text('第一条'), findsOneWidget);
    expect(find.byKey(const Key('chat-typing-indicator')), findsOneWidget);
    expect(find.text('等待'), findsNothing);
    expect(
      tester.widget<TextField>(find.byKey(const Key('chat-input'))).enabled,
      isTrue,
    );
    expect(
      tester
          .widget<IconButton>(find.byKey(const Key('chat-sticker-button')))
          .onPressed,
      isNotNull,
    );

    await tester.enterText(find.byKey(const Key('chat-input')), '第二条');
    await tester.pump();
    await tester.tap(find.byKey(const Key('chat-send-button')));
    await tester.pump();
    expect(repository.acceptTextCalls, 2);
    expect(find.text('第二条'), findsOneWidget);

    repository.emit(
      ChatEvent(
        type: ChatEventType.delivery,
        presentation: const ChatDeliveryPresentation(
          messageDelaysMs: <int>[0, 0],
        ),
        messages: <ChatMessage>[
          ChatMessage(
            id: 10,
            sender: ChatMessageSender.assistant,
            content: '我都看到了。',
            createdAt: DateTime.now(),
          ),
          ChatMessage(
            id: 11,
            sender: ChatMessageSender.assistant,
            content: '你接着说。',
            createdAt: DateTime.now().add(const Duration(milliseconds: 1)),
          ),
        ],
      ),
    );
    repository.emit(
      const ChatEvent(type: ChatEventType.typingStopped, turnId: 'turn-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('我都看到了。'), findsOneWidget);
    expect(find.text('你接着说。'), findsOneWidget);
  });

  testWidgets('opens saved stickers and sends the tapped item immediately', (
    tester,
  ) async {
    final chatRepository = FakeChatRepository();
    final stickerRepository = sticker_fakes.FakeStickersRepository(
      items: [
        sticker_fakes.stickerFixture(
          stickerId: 'wave',
          url: 'https://cdn.example.test/wave.png',
          description: '开心挥手',
        ),
      ],
    );
    await _pumpChat(
      tester,
      chatRepository,
      stickerRepository: stickerRepository,
    );

    await tester.tap(find.byKey(const Key('chat-sticker-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.byKey(const ValueKey<String>('send-sticker-wave')));
    await tester.pumpAndSettle();

    expect(chatRepository.acceptStickerCalls, 1);
    expect(chatRepository.sentStickers.single.stickerId, 'wave');
    expect(
      find.byKey(const ValueKey<String>('chat-sticker-image-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('chat-text-bubble-1')),
      findsNothing,
    );
  });

  testWidgets('renders Echo text and sticker as separate messages', (
    tester,
  ) async {
    final repository = FakeChatRepository();
    await _pumpChat(tester, repository);
    await tester.tap(find.byKey(const Key('chat-expand-toggle')));
    await tester.pumpAndSettle();
    repository.emit(
      ChatEvent(
        type: ChatEventType.delivery,
        presentation: const ChatDeliveryPresentation(
          messageDelaysMs: <int>[0, 0],
        ),
        messages: <ChatMessage>[
          ChatMessage(
            id: 20,
            sender: ChatMessageSender.assistant,
            content: '给你。',
            createdAt: DateTime.now(),
          ),
          ChatMessage(
            id: 21,
            sender: ChatMessageSender.assistant,
            content: '',
            sticker: const ChatSticker(
              stickerId: 'echo-wave',
              url: 'https://cdn.example.test/echo-wave.png',
            ),
            createdAt: DateTime.now().add(const Duration(milliseconds: 1)),
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('给你。'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('chat-sticker-image-21')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('chat-text-bubble-21')),
      findsNothing,
    );
  });

  testWidgets(
    'clear confirmation explains memory and restores restart greeting',
    (tester) async {
      final repository = FakeChatRepository();
      await _pumpChat(tester, repository, preferredName: '小叶');

      await tester.tap(find.byTooltip('聊天菜单'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('清除聊天上下文'));
      await tester.pumpAndSettle();

      expect(find.text('会清除聊天记录和会话摘要，长期记忆仍会保留。'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, '清除'));
      await tester.pumpAndSettle();

      expect(repository.clearCalls, 1);
      expect(find.text('好啦，小叶。我们重新聊。'), findsOneWidget);
      expect(find.text('聊天上下文已清除'), findsOneWidget);
    },
  );
}

Future<void> _pumpChat(
  WidgetTester tester,
  FakeChatRepository repository, {
  String preferredName = '',
  int unreadLetterCount = 0,
  String installedAppVersion = '1.0.5',
  sticker_fakes.FakeStickersRepository? stickerRepository,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        chatRepositoryProvider.overrideWithValue(repository),
        chatPreferredNameProvider.overrideWithValue(preferredName),
        lettersUnreadCountProvider.overrideWithValue(unreadLetterCount),
        installedAppVersionProvider.overrideWith(
          (ref) async => installedAppVersion.split('+').first,
        ),
        if (stickerRepository != null)
          secureStoreProvider.overrideWithValue(
            FakeSessionStore(testSession()),
          ),
        if (stickerRepository != null)
          stickersRepositoryProvider.overrideWithValue(stickerRepository),
      ],
      child: const MaterialApp(home: ChatPage()),
    ),
  );
  await tester.pumpAndSettle();
  while (repository.watchEventCalls == 0) {
    await tester.pump();
  }
}
