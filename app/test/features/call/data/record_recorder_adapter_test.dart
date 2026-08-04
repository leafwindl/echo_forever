import 'package:echo_app/features/call/data/record_recorder_adapter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';

void main() {
  test('call recorder leaves Android audio focus to AudioSessionAdapter', () {
    final config = RecordRecorderAdapter.streamConfig;

    expect(config.encoder, AudioEncoder.pcm16bits);
    expect(config.sampleRate, 16000);
    expect(config.numChannels, 1);
    expect(config.streamBufferSize, 6400);
    expect(config.audioInterruption, AudioInterruptionMode.none);
  });
}
