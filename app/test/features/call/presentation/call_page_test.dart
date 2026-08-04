import 'package:echo_app/features/call/data/call_providers.dart';
import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:echo_app/features/call/presentation/call_controller.dart';
import 'package:echo_app/features/call/presentation/call_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes.dart';

void main() {
  testWidgets('renders idle, recording and partial subtitle states', (
    tester,
  ) async {
    final fixtures = _WidgetFixtures();
    await fixtures.pump(tester);

    expect(find.text('按住下方按钮说话'), findsOneWidget);
    expect(find.byKey(const Key('call-character')), findsOneWidget);
    expect(find.byKey(const Key('call-talk-button')), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CallPage)),
    );
    await container.read(callControllerProvider.notifier).startRecording();
    await tester.pump();
    fixtures.socket.emit(const VoiceStreamEvent.ready());
    fixtures.socket.emit(const VoiceStreamEvent.partial('这是一段临时字幕'));
    await tester.pump();

    expect(find.text('正在听你说'), findsOneWidget);
    expect(find.text('你：这是一段临时字幕'), findsOneWidget);
    expect(find.text('松开发送'), findsOneWidget);
  });

  testWidgets('shows a stable permission-denied explanation', (tester) async {
    final fixtures = _WidgetFixtures()..recorder.permitted = false;
    await fixtures.pump(tester);
    final container = ProviderScope.containerOf(
      tester.element(find.byType(CallPage)),
    );

    expect(
      await container.read(callControllerProvider.notifier).startRecording(),
      isFalse,
    );
    await tester.pump();

    expect(find.byKey(const Key('call-error')), findsOneWidget);
    expect(find.text('需要麦克风权限才能和 Echo 通话。'), findsOneWidget);
  });
}

class _WidgetFixtures {
  final FakeRecorderAdapter recorder = FakeRecorderAdapter();
  final FakeVoiceSocketSession socket = FakeVoiceSocketSession();
  final FakeVoiceUploadClient upload = FakeVoiceUploadClient();
  final FakeCallChatClient chat = FakeCallChatClient();
  final FakeAudioPlayerAdapter player = FakeAudioPlayerAdapter();
  final FakeAudioSessionAdapter audioSession = FakeAudioSessionAdapter();
  final FakeForegroundService foreground = FakeForegroundService();
  final FakeTempAudioStore tempStore = FakeTempAudioStore();

  Future<void> pump(WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          recorderAdapterProvider.overrideWithValue(recorder),
          voiceSocketClientProvider.overrideWithValue(
            FakeVoiceSocketClient(socket),
          ),
          voiceStreamingEnabledProvider.overrideWithValue(true),
          voiceUploadClientProvider.overrideWithValue(upload),
          callChatClientProvider.overrideWithValue(chat),
          audioPlayerAdapterProvider.overrideWithValue(player),
          audioSessionAdapterProvider.overrideWithValue(audioSession),
          callForegroundServiceProvider.overrideWithValue(foreground),
          tempAudioStoreProvider.overrideWithValue(tempStore),
        ],
        child: const MaterialApp(home: CallPage()),
      ),
    );
    await tester.pumpAndSettle();
  }
}
