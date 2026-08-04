import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/routing/auth_redirect.dart';
import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/auth/presentation/auth_controller.dart';
import 'package:echo_app/features/auth/presentation/phone_login_page.dart';
import 'package:echo_app/features/auth/presentation/verification_code_page.dart';
import 'package:echo_app/features/call/presentation/call_page.dart';
import 'package:echo_app/features/chat/presentation/chat_page.dart';
import 'package:echo_app/shared/widgets/echo_error_view.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class RouterRefreshNotifier extends ChangeNotifier {
  void refresh() => notifyListeners();
}

final appRouterProvider = Provider<GoRouter>((ref) {
  final refreshNotifier = RouterRefreshNotifier();
  ref
    ..listen(sessionControllerProvider, (_, _) => refreshNotifier.refresh())
    ..listen(
      authControllerProvider.select((state) => state.verification != null),
      (_, _) => refreshNotifier.refresh(),
    )
    ..onDispose(refreshNotifier.dispose);

  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: refreshNotifier,
    redirect: (context, state) => authRedirect(
      location: state.matchedLocation,
      session: ref.read(sessionControllerProvider),
      hasVerification: ref.read(authControllerProvider).verification != null,
    ),
    routes: <RouteBase>[
      GoRoute(
        path: '/splash',
        name: RouteNames.splash,
        builder: (context, state) => const Scaffold(body: EchoLoadingView()),
      ),
      GoRoute(
        path: '/login',
        name: RouteNames.login,
        builder: (context, state) => const PhoneLoginPage(),
      ),
      GoRoute(
        path: '/verify',
        name: RouteNames.verification,
        builder: (context, state) {
          final verification = ref.read(authControllerProvider).verification;
          return verification == null
              ? const Scaffold(body: EchoLoadingView())
              : VerificationCodePage(verification: verification);
        },
      ),
      GoRoute(
        path: '/home',
        name: RouteNames.home,
        builder: (context, state) => const ChatPage(),
      ),
      GoRoute(
        path: '/call',
        name: RouteNames.call,
        builder: (context, state) => const CallPage(),
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(),
      body: EchoErrorView(message: '页面不存在：${state.uri.path}'),
    ),
  );
});
