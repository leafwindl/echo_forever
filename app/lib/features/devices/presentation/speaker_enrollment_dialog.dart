import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:echo_app/features/devices/domain/device.dart';
import 'package:echo_app/features/devices/presentation/device_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';

class SpeakerEnrollmentDialog extends ConsumerStatefulWidget {
  const SpeakerEnrollmentDialog({super.key, required this.device});

  final EchoDevice device;

  @override
  ConsumerState<SpeakerEnrollmentDialog> createState() =>
      _SpeakerEnrollmentDialogState();
}

class _SpeakerEnrollmentDialogState
    extends ConsumerState<SpeakerEnrollmentDialog> {
  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<Uint8List>? _recordingSubscription;
  Completer<void>? _recordingDone;
  final List<int> _audio = [];
  Timer? _timer;
  Duration _elapsed = Duration.zero;
  bool _recording = false;
  bool _uploading = false;
  String? _message;

  @override
  void dispose() {
    _timer?.cancel();
    _recordingSubscription?.cancel();
    _recorder.dispose();
    super.dispose();
  }

  Future<void> _startRecording() async {
    if (_uploading) return;
    if (!await _recorder.hasPermission()) {
      setState(
        () =>
            _message = '\u8bf7\u5141\u8bb8 Echo \u4f7f\u7528\u9ea6\u514b\u98ce',
      );
      return;
    }
    _audio.clear();
    _elapsed = Duration.zero;
    _message =
        '\u8bf7\u8bf4\u4e00\u53e5\u5e73\u65f6\u7684\u8bdd\uff0c\u5efa\u8bae\u5f55\u97f3 3 \u79d2';
    final stream = await _recorder.startStream(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
        echoCancel: false,
        noiseSuppress: false,
        autoGain: false,
        streamBufferSize: 4096,
      ),
    );
    _recordingDone = Completer<void>();
    _recordingSubscription = stream.listen(
      _audio.addAll,
      onDone: () {
        if (!(_recordingDone?.isCompleted ?? true)) {
          _recordingDone!.complete();
        }
      },
    );
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _elapsed += const Duration(seconds: 1));
    });
    if (mounted) setState(() => _recording = true);
  }

  Future<void> _stopRecording() async {
    _timer?.cancel();
    await _recorder.stop();
    try {
      await _recordingDone?.future.timeout(const Duration(seconds: 2));
    } on TimeoutException {
      await _recordingSubscription?.cancel();
    }
    _recordingSubscription = null;
    _recordingDone = null;
    if (!mounted) return;
    if (_audio.length < 16000 * 2) {
      setState(() {
        _recording = false;
        _message =
            '\u8bf7\u81f3\u5c11\u5f55\u97f3 1 \u79d2\uff0c\u518d\u7ed3\u675f\u5f55\u97f3';
      });
      return;
    }
    final peak = _peakPcm16(_audio);
    if (peak < 300) {
      setState(() {
        _recording = false;
        _message =
            '\u6ca1\u6709\u68c0\u6d4b\u5230\u6709\u6548\u58f0\u97f3\uff0c\u8bf7\u68c0\u67e5\u9ea6\u514b\u98ce\u6743\u9650\u540e\u91cd\u8bd5';
      });
      return;
    }
    setState(() {
      _recording = false;
      _uploading = true;
      _message = '\u6b63\u5728\u68c0\u6d4b\u5e76\u4fdd\u5b58\u58f0\u7eb9\u2026';
    });
    final result = await ref
        .read(deviceControllerProvider.notifier)
        .enrollSpeaker(widget.device, _audio);
    if (!mounted) return;
    setState(() {
      _uploading = false;
      final error = ref.read(deviceControllerProvider).asData?.value.error;
      _message = result == null
          ? error?.detail ??
                '\u5f55\u5165\u5931\u8d25\uff0c\u8bf7\u5728\u5b89\u9759\u73af\u5883\u91cd\u8bd5'
          : '\u5df2\u5f55\u5165 ${result.samplesTotal} \u4e2a\u58f0\u7eb9\u6837\u672c\uff0c\u672c\u6b21\u8d28\u91cf ${(result.qualityScore * 100).round()}%';
    });
  }

  int _peakPcm16(List<int> bytes) {
    var peak = 0;
    for (var index = 0; index + 1 < bytes.length; index += 2) {
      final sample = (bytes[index] & 0xff) | (bytes[index + 1] << 8);
      final signed = sample >= 0x8000 ? sample - 0x10000 : sample;
      peak = math.max(peak, signed.abs());
    }
    return peak;
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref
        .watch(deviceControllerProvider)
        .asData
        ?.value
        .speakers[widget.device.deviceId];
    return AlertDialog(
      title: const Text('\u58f0\u7eb9\u8bbe\u7f6e'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            profile == null
                ? '\u5c1a\u672a\u5f55\u5165\u58f0\u7eb9'
                : '\u5df2\u5f55\u5165\u4e3b\u4eba\u58f0\u7eb9',
          ),
          const SizedBox(height: 12),
          Text(
            _message ??
                '\u8bf7\u5f55\u5236 2-5 \u79d2\u6e05\u6670\u8bed\u97f3\uff0c\u53ef\u591a\u6b21\u5f55\u5165\u6765\u63d0\u9ad8\u8bc6\u522b\u7a33\u5b9a\u6027',
          ),
          const SizedBox(height: 18),
          Center(
            child: Text(
              '${_elapsed.inSeconds}s',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
          ),
        ],
      ),
      actions: [
        if (profile != null && !_recording && !_uploading)
          TextButton(
            onPressed: () async {
              await ref
                  .read(deviceControllerProvider.notifier)
                  .deleteSpeaker(widget.device);
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('\u5220\u9664\u58f0\u7eb9'),
          ),
        TextButton(
          onPressed: _recording || _uploading
              ? null
              : () => Navigator.pop(context),
          child: const Text('\u5173\u95ed'),
        ),
        FilledButton.icon(
          onPressed: _uploading
              ? null
              : (_recording ? _stopRecording : _startRecording),
          icon: Icon(_recording ? Icons.stop_rounded : Icons.mic_rounded),
          label: Text(
            _recording
                ? '\u7ed3\u675f\u5f55\u97f3'
                : '\u5f00\u59cb\u5f55\u97f3',
          ),
        ),
      ],
    );
  }
}
