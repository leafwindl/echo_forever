import 'dart:typed_data';

import 'package:echo_app/features/call/domain/pcm_frame_assembler.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PcmFrameAssembler', () {
    test('reframes smaller/equal/larger chunks without losing bytes', () {
      final assembler = PcmFrameAssembler();
      final source = Uint8List.fromList(
        List<int>.generate(6400 * 2 + 73, (index) => index % 251),
      );

      expect(assembler.add(source.sublist(0, 1200)), isEmpty);
      final first = assembler.add(source.sublist(1200, 6400));
      final second = assembler.add(source.sublist(6400));
      final tail = assembler.flush();

      expect(first.single.length, 6400);
      expect(second.single.length, 6400);
      expect(tail.single.length, 73);
      final rebuilt = <int>[
        ...first.expand((frame) => frame),
        ...second.expand((frame) => frame),
        ...tail.expand((frame) => frame),
      ];
      expect(rebuilt, source);
    });

    test('200 ms, 1 second and 60 seconds byte counts match PCM contract', () {
      const bytesPerFrame = 16000 * 2 * 1 ~/ 5;
      expect(bytesPerFrame, 6400);
      expect(bytesPerFrame * 5, 32000);
      expect(bytesPerFrame * 5 * 60, 1920000);
    });
  });
}
