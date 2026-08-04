import 'dart:typed_data';

/// Reframes arbitrary `record` stream chunks into the 200 ms/6400 byte frames
/// required by the streaming ASR contract.  A stop flushes the tail without
/// padding it with fabricated samples.
class PcmFrameAssembler {
  PcmFrameAssembler({this.frameBytes = 6400}) : assert(frameBytes > 0);

  final int frameBytes;
  final BytesBuilder _pending = BytesBuilder(copy: false);

  List<Uint8List> add(Uint8List chunk) {
    if (chunk.isEmpty) return const <Uint8List>[];
    _pending.add(chunk);
    return _takeFullFrames();
  }

  List<Uint8List> flush() {
    final result = _takeFullFrames();
    if (_pending.length > 0) {
      result.add(Uint8List.fromList(_pending.takeBytes()));
    }
    return result;
  }

  List<Uint8List> _takeFullFrames() {
    final result = <Uint8List>[];
    while (_pending.length >= frameBytes) {
      final bytes = _pending.takeBytes();
      result.add(Uint8List.fromList(bytes.sublist(0, frameBytes)));
      final rest = bytes.sublist(frameBytes);
      if (rest.isNotEmpty) _pending.add(rest);
    }
    return result;
  }

  int get pendingBytes => _pending.length;

  void clear() => _pending.takeBytes();
}
