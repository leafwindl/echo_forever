import 'dart:io';

import 'package:path_provider/path_provider.dart';

class TempAudioStore {
  const TempAudioStore();

  static const _prefix = 'echo_call_';

  Future<void> delete(String path) async {
    final file = File(path);
    if (await file.exists()) await file.delete();
  }

  Future<void> cleanupOrphans({
    Duration maxAge = const Duration(hours: 12),
  }) async {
    final directory = await getTemporaryDirectory();
    if (!await directory.exists()) return;
    final cutoff = DateTime.now().subtract(maxAge);
    await for (final entity in directory.list(followLinks: false)) {
      if (entity is! File ||
          !entity.uri.pathSegments.last.startsWith(_prefix)) {
        continue;
      }
      try {
        final modified = await entity.lastModified();
        if (modified.isBefore(cutoff)) await entity.delete();
      } on FileSystemException {
        // Cache cleanup is best effort and never blocks app startup.
      }
    }
  }
}
