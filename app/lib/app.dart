import 'dart:async';

import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/routing/app_router.dart';
import 'package:echo_app/core/theme/app_theme.dart';
import 'package:echo_app/features/letters/presentation/letters_controller.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:echo_app/features/push/data/push_providers.dart';
import 'package:echo_app/features/push/domain/push_notification.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final echoScaffoldMessengerKey = GlobalKey<ScaffoldMessengerState>();

class EchoApp extends ConsumerWidget {
  const EchoApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);

    void replayPendingRoute() {
      final session = ref.read(sessionControllerProvider).asData?.value;
      final persona = ref.read(personaControllerProvider);
      final pending = ref.read(pushControllerProvider).pending;
      if (pending == null || session?.isAuthenticated != true) return;
      // Keep the intent through onboarding; the router guard can only target
      // the requested feature after the required persona setup is complete.
      if (persona.asData?.value.onboardingCompleted != true) return;
      router.go(pending.navigationLocation);
      ref.read(pushControllerProvider.notifier).takePending();
    }

    ref.listen<bool>(
      sessionControllerProvider.select(
        (state) => state.asData?.value.isAuthenticated ?? false,
      ),
      (previous, next) {
        if (next && previous != true) {
          unawaited(
            ref.read(pushControllerProvider.notifier).registerCurrentToken(),
          );
          replayPendingRoute();
        }
      },
    );
    ref.listen<bool>(
      personaControllerProvider.select(
        (state) => state.asData?.value.onboardingCompleted ?? false,
      ),
      (_, next) {
        if (next) replayPendingRoute();
      },
    );
    ref.listen<PushNotification?>(
      pushControllerProvider.select((state) => state.pending),
      (_, next) {
        final pending = next;
        if (pending == null) return;
        replayPendingRoute();
      },
    );
    ref.listen<PushNotification?>(
      pushControllerProvider.select((state) => state.foregroundNotification),
      (_, next) {
        final messenger = echoScaffoldMessengerKey.currentState;
        if (next == null || messenger == null) return;
        if (next.route == 'letters') {
          ref.invalidate(lettersControllerProvider);
        }
        messenger
          ..hideCurrentSnackBar()
          ..showSnackBar(
            SnackBar(
              content: Text(_foregroundMessage(next)),
              action: SnackBarAction(
                label: '查看',
                onPressed: () {
                  router.go(next.navigationLocation);
                  ref
                      .read(pushControllerProvider.notifier)
                      .dismissForegroundNotification();
                },
              ),
            ),
          );
        ref
            .read(pushControllerProvider.notifier)
            .dismissForegroundNotification();
      },
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (context.mounted) replayPendingRoute();
    });

    return MaterialApp.router(
      title: 'Echo',
      debugShowCheckedModeBanner: false,
      scaffoldMessengerKey: echoScaffoldMessengerKey,
      theme: AppTheme.light,
      routerConfig: router,
    );
  }

  String _foregroundMessage(PushNotification notification) {
    return switch (notification.type) {
      'letter_ready' => 'Echo 有一封新来信',
      _ => 'Echo 有新的提醒',
    };
  }
}
