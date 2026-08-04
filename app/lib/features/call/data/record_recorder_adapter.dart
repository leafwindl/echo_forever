import 'dart:async';
import 'dart:io';

import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

class RecordRecorderAdapter implements RecorderAdapter {
  RecordRecorderAdapter({AudioRecorder? recorder})
    : _recorder = recorder ?? AudioRecorder();

  @visibleForTesting
  static const streamConfig = RecordConfig(
    encoder: AudioEncoder.pcm16bits,
    sampleRate: 16000,
    numChannels: 1,
    bitRate: 256000,
    streamBufferSize: 6400,
    // AudioSessionAdapter owns focus for the whole call. Letting record request
    // a second focus lease can report a false interruption on Android.
    audioInterruption: AudioInterruptionMode.none,
  );

  final AudioRecorder _recorder;
  final StreamController<Uint8List> _chunks =
      StreamController<Uint8List>.broadcast();
  final StreamController<double> _amplitude =
      StreamController<double>.broadcast();
  StreamSubscription<Uint8List>? _recordSubscription;
  StreamSubscription<Amplitude>? _amplitudeSubscription;
  Future<void> _writeChain = Future<void>.value();
  File? _spool;
  Stopwatch? _stopwatch;
  int _bytes = 0;
  bool _started = false;

  @override
  Stream<Uint8List> get chunks => _chunks.stream;

  @override
  Stream<double> get amplitude => _amplitude.stream;

  @override
  Future<bool> requestPermission() => _recorder.hasPermission();

  @override
  Future<void> start() async {
    if (_started) return;
    final directory = await getTemporaryDirectory();
    _spool = File(
      '${directory.path}${Platform.pathSeparator}echo_call_${DateTime.now().microsecondsSinceEpoch}.pcm',
    );
    await _spool!.create(recursive: true);
    _writeChain = Future<void>.value();
    _bytes = 0;
    _stopwatch = Stopwatch()..start();
    final stream = await _recorder.startStream(streamConfig);
    _started = true;
    _recordSubscription = stream.listen((chunk) {
      if (chunk.isEmpty) return;
      _bytes += chunk.length;
      _writeChain = _writeChain.then(
        (_) => _spool!.writeAsBytes(chunk, mode: FileMode.append, flush: false),
      );
      _chunks.add(Uint8List.fromList(chunk));
    }, onError: _chunks.addError);
    _amplitudeSubscription = _recorder
        .onAmplitudeChanged(const Duration(milliseconds: 100))
        .listen((value) {
          final normalized = ((value.current + 60) / 60).clamp(0.0, 1.0);
          _amplitude.add(normalized);
        }, onError: (_) {});
  }

  @override
  Future<RecordingResult> stop() async {
    if (!_started || _spool == null) {
      throw StateError('Recorder is not active');
    }
    await _recorder.stop();
    await _recordSubscription?.cancel();
    await _amplitudeSubscription?.cancel();
    await _writeChain;
    _stopwatch?.stop();
    final result = RecordingResult(
      path: _spool!.path,
      format: VoiceAudioFormat.pcm16le,
      bytes: _bytes,
      duration: _stopwatch?.elapsed ?? Duration.zero,
    );
    _recordSubscription = null;
    _amplitudeSubscription = null;
    _spool = null;
    _stopwatch = null;
    _started = false;
    return result;
  }

  @override
  Future<void> cancel() async {
    if (_started) {
      await _recorder.cancel();
      await _recordSubscription?.cancel();
      await _amplitudeSubscription?.cancel();
    }
    final path = _spool?.path;
    _spool = null;
    _recordSubscription = null;
    _amplitudeSubscription = null;
    _stopwatch = null;
    _started = false;
    if (path != null) {
      try {
        await File(path).delete();
      } on FileSystemException {
        // The cache cleanup on next launch is the safety net.
      }
    }
  }

  @override
  Future<void> dispose() async {
    await cancel();
    await _recorder.dispose();
    await _chunks.close();
    await _amplitude.close();
  }
}
