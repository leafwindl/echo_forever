import 'package:echo_app/features/call/domain/audio_segment_queue.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'player queue preserves valid TTS segment order and drops unsafe URLs',
    () {
      final queue = AudioSegmentQueue.sanitize(<String>[
        'https://cdn.example.test/one.mp3',
        'javascript:alert(1)',
        'http://cdn.example.test/two.mp3',
        'not a url',
        'https://cdn.example.test/three.mp3',
      ]);

      expect(queue.map((uri) => uri.toString()), <String>[
        'https://cdn.example.test/one.mp3',
        'http://cdn.example.test/two.mp3',
        'https://cdn.example.test/three.mp3',
      ]);
    },
  );
}
