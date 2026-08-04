import 'dart:async';

import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/features/call/data/temp_audio_store.dart';
import 'package:echo_app/features/push/presentation/push_controller.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void bootstrap(Widget app) {
  WidgetsFlutterBinding.ensureInitialized();
  unawaited(const TempAudioStore().cleanupOrphans());
  runApp(ProviderScope(child: _PushBootstrap(child: app)));
}

class _PushBootstrap extends ConsumerStatefulWidget {
  const _PushBootstrap({required this.child});

  final Widget child;

  @override
  ConsumerState<_PushBootstrap> createState() => _PushBootstrapState();
}

class _PushBootstrapState extends ConsumerState<_PushBootstrap> {
  @override
  void initState() {
    super.initState();
    unawaited(_restoreSessionThenInitializePush());
  }

  Future<void> _restoreSessionThenInitializePush() async {
    // Restore secure session first so the initial FCM token can be registered
    // for the correct account.
    await ref.read(sessionControllerProvider.future);
    await ref.read(pushControllerProvider.notifier).initialize();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
