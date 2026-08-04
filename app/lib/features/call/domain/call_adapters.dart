import 'dart:async';
import 'dart:typed_data';

import 'package:echo_app/features/call/domain/call_models.dart';

abstract interface class RecorderAdapter {
  Future<bool> requestPermission();

  Future<void> start();

  Stream<Uint8List> get chunks;

  Stream<double> get amplitude;

  Future<RecordingResult> stop();

  Future<void> cancel();

  Future<void> dispose();
}

abstract interface class VoiceSocketSession {
  Stream<VoiceStreamEvent> get events;

  /// Completes when the server's initial `ready` frame has been received.
  ///
  /// The socket may receive that frame before the caller attaches its event
  /// listener, so readiness is exposed separately from the event stream.
  Future<void> get ready;

  /// Returns false when the bounded outbound queue is saturated.
  bool sendAudio(Uint8List bytes);

  Future<String> finish();

  Future<void> cancel();

  Future<void> close();
}

abstract interface class VoiceSocketClient {
  Future<VoiceSocketSession> open({required String requestId});
}

abstract interface class VoiceUploadClient {
  Future<String> recognize(RecordingResult recording);
}

abstract interface class AudioPlayerAdapter {
  Future<void> stop();

  Future<void> playSegments(
    List<String> urls, {
    required bool Function() shouldContinue,
  });

  Future<void> dispose();
}

abstract interface class AudioSessionAdapter {
  Future<void> configure();

  Future<void> beginRecording();

  Future<void> beginPlayback();

  Future<void> release();

  Stream<bool> get interruptionStream;
}

abstract interface class CallForegroundService {
  Future<void> start({required Future<void> Function() onStopRequested});

  Future<void> stopService();
}
