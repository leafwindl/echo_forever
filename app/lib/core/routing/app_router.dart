import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/routing/auth_redirect.dart';
import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/auth/presentation/auth_controller.dart';
import 'package:echo_app/features/auth/presentation/phone_login_page.dart';
import 'package:echo_app/features/auth/presentation/verification_code_page.dart';
import 'package:echo_app/features/call/presentation/call_page.dart';
import 'package:echo_app/features/chat/presentation/chat_page.dart';
import 'package:echo_app/features/letters/presentation/letters_page.dart';
import 'package:echo_app/features/memory/presentation/memory_page.dart';
import 'package:echo_app/features/onboarding/presentation/onboarding_page.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:echo_app/features/persona/presentation/persona_page.dart';
import 'package:echo_app/features/stickers/presentation/stickers_page.dart';
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
    ..listen(personaControllerProvider, (_, _) => refreshNotifier.refresh())
    ..listen(
      authControllerProvider.select((state) => state.verification != null),
      (_, _) => refreshNotifier.refresh(),
    )
    ..onDispose(refreshNotifier.dispose);

  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: refreshNotifier,
    redirect: (context, state) {
      final location = state.matchedLocation;
      final session = ref.read(sessionControllerProvider);
      final authTarget = authRedirect(
        location: location,
        session: session,
        hasVerification: ref.read(authControllerProvider).verification != null,
      );
      if (authTarget != null) {
        if (authTarget == '/home') {
          return _onboardingRedirect(
                location: location,
                session: session,
                persona: ref.read(personaControllerProvider),
              ) ??
              authTarget;
        }
        return authTarget;
      }
      return _onboardingRedirect(
        location: location,
        session: session,
        persona: ref.read(personaControllerProvider),
      );
    },
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
        path: '/onboarding',
        name: RouteNames.onboarding,
        builder: (context, state) => const OnboardingPage(),
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
      GoRoute(
        path: '/persona',
        name: RouteNames.persona,
        builder: (context, state) => const PersonaPage(),
      ),
      GoRoute(
        path: '/memory',
        name: RouteNames.memory,
        builder: (context, state) => const MemoryPage(),
      ),
      GoRoute(
        path: '/letters',
        name: RouteNames.letters,
        builder: (context, state) => const LettersPage(),
      ),
      GoRoute(
        path: '/stickers',
        name: RouteNames.stickers,
        builder: (context, state) => const StickersPage(),
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(),
      body: EchoErrorView(message: '椤甸潰涓嶅瓨鍦細${state.uri.path}'),
    ),
  );
});

String? _onboardingRedirect({
  required String location,
  required AsyncValue<SessionSnapshot> session,
  required AsyncValue<PersonaState> persona,
}) {
  final isAuthenticated = session.asData?.value.isAuthenticated ?? false;
  if (!isAuthenticated) {
    return null;
  }
  if (persona.isLoading) {
    return location == '/splash' ? null : '/splash';
  }
  final completed = persona.asData?.value.onboardingCompleted ?? false;
  final isOnboardingLocation = location == '/onboarding';
  if (!completed) {
    return isOnboardingLocation ? null : '/onboarding';
  }
  if (isOnboardingLocation) {
    return '/home';
  }
  return null;
}
