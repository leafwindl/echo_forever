import 'dart:async';

import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/secure_store.dart';
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
  });

  testWidgets('shows the unread letter badge in the chat toolbar', (
    tester,
  ) async {
    await _pumpChat(tester, FakeChatRepository(), unreadLetterCount: 3);

    expect(find.byKey(const Key('open-letters-button')), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });

  testWidgets('shows typing immediately and replaces it with reply', (
    tester,
  ) async {
    final gate = Completer<ChatReply>();
    final repository = FakeChatRepository(onSend: (_, _) => gate.future);
    await _pumpChat(tester, repository);

    await tester.enterText(find.byKey(const Key('chat-input')), '今天有点累');
    await tester.pump();
    await tester.tap(find.byKey(const Key('chat-send-button')));
    await tester.pumpAndSettle();

    expect(find.text('今天有点累'), findsOneWidget);
    expect(find.byKey(const Key('chat-typing-indicator')), findsOneWidget);
    expect(find.text('等待'), findsOneWidget);
    expect(repository.sendCalls, 1);

    gate.complete(const ChatReply(reply: '那就先休息一下，我陪着你。'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('chat-typing-indicator')), findsNothing);
    expect(find.text('那就先休息一下，我陪着你。'), findsOneWidget);
    expect(find.text('发送'), findsOneWidget);
  });

  testWidgets('opens saved stickers and sends the tapped item immediately', (
    tester,
  ) async {
    final chatRepository = FakeChatRepository(
      onSendSticker: (_, _) async => const ChatReply(reply: '收到你的表情啦。'),
    );
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
    expect(
      find.byKey(const ValueKey<String>('send-sticker-wave')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey<String>('send-sticker-wave')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(chatRepository.sendStickerCalls, 1);
    expect(chatRepository.sentStickers.single.stickerId, 'wave');
    final container = ProviderScope.containerOf(
      tester.element(find.byType(ChatPage)),
    );
    expect(
      container.read(chatControllerProvider).messages.last.content,
      '收到你的表情啦。',
    );
    expect(
      find.byKey(const ValueKey<String>('chat-sticker-image-2')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('chat-text-bubble-2')),
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

  testWidgets('expands chat and keeps the latest reply in the list viewport', (
    tester,
  ) async {
    var replyNumber = 0;
    final repository = FakeChatRepository(
      onSend: (_, _) async => ChatReply(reply: '回复 ${replyNumber++}'),
    );
    await _pumpChat(tester, repository);

    await tester.tap(find.byKey(const Key('chat-expand-toggle')));
    await tester.pumpAndSettle();
    expect(find.text('▼ 收起聊天'), findsOneWidget);
    expect(find.byKey(const Key('character-sitting-image')), findsOneWidget);

    for (var index = 0; index < 8; index += 1) {
      await tester.enterText(find.byKey(const Key('chat-input')), '消息 $index');
      await tester.pump();
      await tester.tap(find.byKey(const Key('chat-send-button')));
      await tester.pumpAndSettle();
    }

    final container = ProviderScope.containerOf(
      tester.element(find.byType(ChatPage)),
    );
    expect(repository.sendCalls, 8);
    expect(
      container.read(chatControllerProvider).messages.last.content,
      '回复 7',
    );
    await tester.pump(const Duration(milliseconds: 300));
    final latestReply = find.text('回复 7');
    expect(latestReply, findsOneWidget);
    final listBottom = tester
        .getBottomRight(find.byKey(const Key('chat-message-list')))
        .dy;
    expect(
      tester.getBottomRight(latestReply).dy,
      lessThanOrEqualTo(listBottom),
    );
  });
}

Future<void> _pumpChat(
  WidgetTester tester,
  FakeChatRepository repository, {
  String preferredName = '',
  int unreadLetterCount = 0,
  sticker_fakes.FakeStickersRepository? stickerRepository,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        chatRepositoryProvider.overrideWithValue(repository),
        chatPreferredNameProvider.overrideWithValue(preferredName),
        lettersUnreadCountProvider.overrideWithValue(unreadLetterCount),
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
}
