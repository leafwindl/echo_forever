import 'dart:async';

import 'package:echo_app/features/call/data/call_providers.dart';
import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:echo_app/features/call/presentation/call_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes.dart';

void main() {
  test(
    'WS protocol sends binary frames then stop and handles partial/final',
    () async {
      final fixtures = _CallFixtures();
      final container = fixtures.container();
      addTearDown(container.dispose);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);
      final controller = container.read(callControllerProvider.notifier);

      await controller.connect();
      expect(await controller.startRecording(), isTrue);
      await container.pump();
      fixtures.socket.emit(const VoiceStreamEvent.ready());
      fixtures.recorder.emit(List<int>.generate(6400, (index) => index % 127));
      fixtures.socket.emit(const VoiceStreamEvent.partial('你'));
      fixtures.socket.emit(const VoiceStreamEvent.partial('你好'));

      expect(container.read(callControllerProvider).partialText, '你好');
      expect(await controller.stopRecording(), isTrue);

      expect(fixtures.socket.sentFrames.map((frame) => frame.length), <int>[
        6400,
      ]);
      expect(fixtures.socket.controls, contains('stop'));
      expect(fixtures.upload.calls, 0);
      expect(fixtures.chat.messages, <String>['测试 final']);
      expect(fixtures.player.queues.single, <String>[
        'https://audio.example.test/1.mp3',
      ]);
      expect(container.read(callControllerProvider).phase, CallPhase.idle);
      expect(container.read(callControllerProvider).echoCaption, 'Echo 回复');
    },
  );

  test('falls back to whole-file ASR once and sends chat once', () async {
    final fixtures = _CallFixtures(socketOpenError: StateError('offline'));
    final container = fixtures.container();
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    final controller = container.read(callControllerProvider.notifier);

    await controller.connect();
    await controller.startRecording();
    await container.pump();
    fixtures.recorder.emit(List<int>.filled(3200, 1));
    expect(await controller.stopRecording(), isTrue);

    expect(fixtures.upload.calls, 1);
    expect(fixtures.chat.messages, <String>['fallback final']);
    expect(fixtures.chat.messages, hasLength(1));
    expect(fixtures.tempStore.deleted, <String>['fake.pcm']);
  });

  test('batch mode records first and uploads once after release', () async {
    final fixtures = _CallFixtures(streamingEnabled: false);
    final container = fixtures.container();
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    final controller = container.read(callControllerProvider.notifier);

    await controller.connect();
    expect(await controller.startRecording(), isTrue);
    fixtures.recorder.emit(List<int>.filled(6400, 4));

    expect(await controller.stopRecording(), isTrue);
    expect(fixtures.socketClient.openCalls, 0);
    expect(fixtures.upload.calls, 1);
    expect(fixtures.chat.messages, <String>['fallback final']);
  });

  test('stop waits for an in-flight socket to become ready', () async {
    final openGate = Completer<void>();
    final fixtures = _CallFixtures(socketOpenGate: openGate.future);
    final container = fixtures.container();
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    final controller = container.read(callControllerProvider.notifier);

    await controller.connect();
    expect(await controller.startRecording(), isTrue);
    fixtures.recorder.emit(List<int>.filled(6400, 3));

    final stopping = controller.stopRecording();
    await container.pump();
    expect(container.read(callControllerProvider).phase, CallPhase.recognizing);
    expect(fixtures.upload.calls, 0);

    openGate.complete();
    fixtures.socket.emit(const VoiceStreamEvent.ready());

    expect(await stopping, isTrue);
    expect(fixtures.socket.controls, contains('stop'));
    expect(fixtures.upload.calls, 0);
    expect(fixtures.chat.messages, <String>['测试 final']);
  });

  test(
    'manual user interruption stops speaking and starts a new turn',
    () async {
      final fixtures = _CallFixtures();
      final container = fixtures.container();
      addTearDown(container.dispose);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);
      final controller = container.read(callControllerProvider.notifier);

      await controller.connect();
      await controller.startRecording();
      await container.pump();
      fixtures.socket.emit(const VoiceStreamEvent.ready());
      fixtures.recorder.emit(List<int>.filled(6400, 2));
      // The first startRecording performs a defensive player stop, so gate
      // only the playback belonging to this completed utterance.
      fixtures.player.playGate = Completer<void>();
      final firstTurn = controller.stopRecording();
      await fixtures.player.playStarted.future.timeout(
        const Duration(seconds: 1),
      );

      expect(container.read(callControllerProvider).phase, CallPhase.speaking);

      expect(await controller.startRecording(), isTrue);
      expect(container.read(callControllerProvider).phase, CallPhase.recording);
      expect(fixtures.player.stopCalls, greaterThanOrEqualTo(2));
      expect(await firstTurn, isTrue);
      await controller.cancelRecording();
    },
  );

  test(
    'system interruption cancels an active utterance without chat',
    () async {
      final fixtures = _CallFixtures();
      final container = fixtures.container();
      addTearDown(container.dispose);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);
      final controller = container.read(callControllerProvider.notifier);

      await controller.connect();
      await controller.startRecording();
      fixtures.audioSession.interruptions.add(true);
      await _pumpUntil(
        container,
        () => container.read(callControllerProvider).phase == CallPhase.idle,
      );

      expect(fixtures.recorder.cancelCalls, 1);
      expect(fixtures.chat.messages, isEmpty);
      expect(container.read(callControllerProvider).phase, CallPhase.idle);
      expect(
        container.read(callControllerProvider).errorMessage,
        contains('系统音频中断'),
      );
    },
  );

  test('hangup cancels resources and notification service', () async {
    final fixtures = _CallFixtures();
    final container = fixtures.container();
    addTearDown(container.dispose);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    final controller = container.read(callControllerProvider.notifier);

    await controller.connect();
    await controller.startRecording();
    await container.pump();
    fixtures.socket.emit(const VoiceStreamEvent.ready());
    await controller.hangUp();

    expect(container.read(callControllerProvider).phase, CallPhase.ended);
    expect(fixtures.recorder.cancelCalls, greaterThanOrEqualTo(1));
    expect(fixtures.socket.controls, contains('close'));
    expect(fixtures.foreground.stopCalls, 1);
    expect(fixtures.audioSession.releaseCalls, 1);
  });
}

class _CallFixtures {
  _CallFixtures({
    Object? socketOpenError,
    Future<void>? socketOpenGate,
    this.streamingEnabled = true,
  }) : socketClient = FakeVoiceSocketClient(
         FakeVoiceSocketSession(),
         openError: socketOpenError,
         openGate: socketOpenGate,
       );

  final FakeRecorderAdapter recorder = FakeRecorderAdapter();
  final FakeVoiceSocketClient socketClient;
  FakeVoiceSocketSession get socket => socketClient.session;
  final FakeVoiceUploadClient upload = FakeVoiceUploadClient();
  final FakeCallChatClient chat = FakeCallChatClient();
  final FakeAudioPlayerAdapter player = FakeAudioPlayerAdapter();
  final FakeAudioSessionAdapter audioSession = FakeAudioSessionAdapter();
  final FakeForegroundService foreground = FakeForegroundService();
  final FakeTempAudioStore tempStore = FakeTempAudioStore();
  final bool streamingEnabled;

  ProviderContainer container() => ProviderContainer(
    overrides: [
      recorderAdapterProvider.overrideWithValue(recorder),
      voiceSocketClientProvider.overrideWithValue(socketClient),
      voiceStreamingEnabledProvider.overrideWithValue(streamingEnabled),
      voiceUploadClientProvider.overrideWithValue(upload),
      callChatClientProvider.overrideWithValue(chat),
      audioPlayerAdapterProvider.overrideWithValue(player),
      audioSessionAdapterProvider.overrideWithValue(audioSession),
      callForegroundServiceProvider.overrideWithValue(foreground),
      tempAudioStoreProvider.overrideWithValue(tempStore),
    ],
  );
}

ProviderSubscription<CallState> _keepAlive(ProviderContainer container) {
  return container.listen<CallState>(
    callControllerProvider,
    (_, _) {},
    fireImmediately: true,
  );
}

Future<void> _pumpUntil(
  ProviderContainer container,
  bool Function() predicate,
) async {
  for (var attempt = 0; attempt < 20 && !predicate(); attempt += 1) {
    await container.pump();
  }
  expect(predicate(), isTrue);
}
