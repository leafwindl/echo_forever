import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/onboarding/presentation/onboarding_page.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:echo_app/shared/widgets/primary_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import '../../../support/fake_session_store.dart';
import '../../persona/fakes.dart';

void main() {
  testWidgets('submits onboarding persona and navigates home', (tester) async {
    final repository = FakePersonaRepository(
      persona: personaFixture(preferredName: null, onboardingCompleted: false),
    );
    final onboarding = FakeOnboardingCompletionStore();
    await _pumpOnboarding(tester, repository, onboarding);

    await tester.enterText(find.byType(TextField).first, 'Leaf');
    await tester.pump();
    await tester.ensureVisible(find.byType(PrimaryButton));
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(PrimaryButton),
        matching: find.byType(FilledButton),
      ),
    );
    await tester.pumpAndSettle();

    expect(repository.updates.single.preferredName, 'Leaf');
    expect(onboarding.completedUsers, contains('user-1'));
    expect(find.byKey(const Key('home-route')), findsOneWidget);
  });
}

Future<void> _pumpOnboarding(
  WidgetTester tester,
  FakePersonaRepository repository,
  FakeOnboardingCompletionStore onboarding,
) async {
  final router = GoRouter(
    initialLocation: '/onboarding',
    routes: <RouteBase>[
      GoRoute(
        path: '/onboarding',
        name: RouteNames.onboarding,
        builder: (context, state) => const OnboardingPage(),
      ),
      GoRoute(
        path: '/home',
        name: RouteNames.home,
        builder: (context, state) => const SizedBox(key: Key('home-route')),
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        secureStoreProvider.overrideWithValue(FakeSessionStore(testSession())),
        personaRepositoryProvider.overrideWithValue(repository),
        onboardingCompletionStoreProvider.overrideWithValue(onboarding),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
  expect(find.byType(OnboardingPage), findsOneWidget);
  expect(
    ProviderScope.containerOf(
      tester.element(find.byType(OnboardingPage)),
    ).read(personaControllerProvider).asData?.value.persona.onboardingCompleted,
    isFalse,
  );
}
