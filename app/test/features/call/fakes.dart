import 'dart:async';
import 'dart:typed_data';

import 'package:echo_app/features/call/data/call_chat_client.dart';
import 'package:echo_app/features/call/data/temp_audio_store.dart';
import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';

class FakeRecorderAdapter implements RecorderAdapter {
  final StreamController<Uint8List> _chunks =
      StreamController<Uint8List>.broadcast(sync: true);
  final StreamController<double> _amplitude =
      StreamController<double>.broadcast(sync: true);
  bool permitted = true;
  bool started = false;
  int startCalls = 0;
  int stopCalls = 0;
  int cancelCalls = 0;
  RecordingResult result = const RecordingResult(
    path: 'fake.pcm',
    format: VoiceAudioFormat.pcm16le,
    bytes: 6400,
    duration: Duration(milliseconds: 200),
  );

  @override
  Stream<double> get amplitude => _amplitude.stream;

  @override
  Stream<Uint8List> get chunks => _chunks.stream;

  void emit(List<int> bytes) => _chunks.add(Uint8List.fromList(bytes));

  void emitAmplitude(double value) => _amplitude.add(value);

  @override
  Future<bool> requestPermission() async => permitted;

  @override
  Future<void> start() async {
    started = true;
    startCalls += 1;
  }

  @override
  Future<RecordingResult> stop() async {
    started = false;
    stopCalls += 1;
    return result;
  }

  @override
  Future<void> cancel() async {
    started = false;
    cancelCalls += 1;
  }

  @override
  Future<void> dispose() async {
    await _chunks.close();
    await _amplitude.close();
  }
}

class FakeVoiceSocketClient implements VoiceSocketClient {
  FakeVoiceSocketClient(this.session, {this.openError, this.openGate});

  final FakeVoiceSocketSession session;
  final Object? openError;
  final Future<void>? openGate;
  int openCalls = 0;

  @override
  Future<VoiceSocketSession> open({required String requestId}) async {
    openCalls += 1;
    await openGate;
    if (openError != null) throw openError!;
    return session;
  }
}

class FakeVoiceSocketSession implements VoiceSocketSession {
  final StreamController<VoiceStreamEvent> _events =
      StreamController<VoiceStreamEvent>.broadcast(sync: true);
  final List<Uint8List> sentFrames = <Uint8List>[];
  final List<String> controls = <String>[];
  String finalText = '测试 final';
  Object? finishError;
  bool acceptFrames = true;
  final Completer<void> readyCompleter = Completer<void>();

  @override
  Stream<VoiceStreamEvent> get events => _events.stream;

  @override
  Future<void> get ready => readyCompleter.future;

  void emit(VoiceStreamEvent event) {
    if (event.type == VoiceStreamEventType.ready &&
        !readyCompleter.isCompleted) {
      readyCompleter.complete();
    }
    _events.add(event);
  }

  @override
  bool sendAudio(Uint8List bytes) {
    if (!acceptFrames) return false;
    sentFrames.add(Uint8List.fromList(bytes));
    return true;
  }

  @override
  Future<String> finish() async {
    controls.add('stop');
    if (finishError != null) throw finishError!;
    emit(VoiceStreamEvent.finalResult(finalText));
    return finalText;
  }

  @override
  Future<void> cancel() async {
    controls.add('cancel');
  }

  @override
  Future<void> close() async {
    controls.add('close');
  }
}

class FakeVoiceUploadClient implements VoiceUploadClient {
  String text = 'fallback final';
  Object? error;
  int calls = 0;

  @override
  Future<String> recognize(RecordingResult recording) async {
    calls += 1;
    if (error != null) throw error!;
    return text;
  }
}

class FakeCallChatClient implements CallChatClient {
  final List<String> messages = <String>[];
  CallChatReply reply = const CallChatReply(
    reply: 'Echo 回复',
    audioUrls: <String>['https://audio.example.test/1.mp3'],
  );

  @override
  Future<CallChatReply> send(String text) async {
    messages.add(text);
    return reply;
  }
}

class FakeAudioPlayerAdapter implements AudioPlayerAdapter {
  final List<List<String>> queues = <List<String>>[];
  final Completer<void> playStarted = Completer<void>();
  Completer<void>? playGate;
  int stopCalls = 0;

  @override
  Future<void> playSegments(
    List<String> urls, {
    required bool Function() shouldContinue,
  }) async {
    queues.add(List<String>.of(urls));
    if (!playStarted.isCompleted) playStarted.complete();
    if (playGate != null) await playGate!.future;
  }

  @override
  Future<void> stop() async {
    stopCalls += 1;
    if (playGate != null && !playGate!.isCompleted) playGate!.complete();
  }

  @override
  Future<void> dispose() async {}
}

class FakeAudioSessionAdapter implements AudioSessionAdapter {
  final StreamController<bool> interruptions = StreamController<bool>.broadcast(
    sync: true,
  );
  int configureCalls = 0;
  int recordingCalls = 0;
  int playbackCalls = 0;
  int releaseCalls = 0;

  @override
  Stream<bool> get interruptionStream => interruptions.stream;

  @override
  Future<void> beginPlayback() async => playbackCalls += 1;

  @override
  Future<void> beginRecording() async => recordingCalls += 1;

  @override
  Future<void> configure() async => configureCalls += 1;

  @override
  Future<void> release() async => releaseCalls += 1;
}

class FakeForegroundService implements CallForegroundService {
  Future<void> Function()? stopCallback;
  int startCalls = 0;
  int stopCalls = 0;

  @override
  Future<void> start({required Future<void> Function() onStopRequested}) async {
    startCalls += 1;
    stopCallback = onStopRequested;
  }

  @override
  Future<void> stopService() async => stopCalls += 1;
}

class FakeTempAudioStore extends TempAudioStore {
  FakeTempAudioStore();

  final List<String> deleted = <String>[];

  @override
  Future<void> delete(String path) async => deleted.add(path);
}
