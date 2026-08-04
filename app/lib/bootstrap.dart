import 'dart:async';

import 'package:echo_app/features/call/data/temp_audio_store.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void bootstrap(Widget app) {
  WidgetsFlutterBinding.ensureInitialized();
  unawaited(const TempAudioStore().cleanupOrphans());
  runApp(ProviderScope(child: app));
}
