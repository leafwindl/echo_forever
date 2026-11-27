import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/presentation/persona_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  testWidgets('shows the relationship stage without internal fields', (
    tester,
  ) async {
    final repository = FakePersonaRepository(
      relationship: const RelationshipStateDto(
        stage: 'familiar',
        stageLabel: '熟悉',
        interactionTurns: 12,
        activeDays: 3,
        affectionPermission: 'welcomed',
        schemaVersion: 3,
      ),
    );
    await tester.pumpWidget(_page(repository));
    await tester.pumpAndSettle();

    expect(find.text('关于她'), findsOneWidget);
    expect(find.text('熟悉'), findsOneWidget);
    expect(find.text('12 次'), findsOneWidget);
    expect(find.text('3 天'), findsOneWidget);
    expect(find.textContaining('welcomed'), findsNothing);
    expect(find.text('AI 恋人'), findsNothing);
    expect(find.textContaining('确认窗口'), findsNothing);
  });
}

Widget _page(FakePersonaRepository repository) => ProviderScope(
  overrides: [
    secureStoreProvider.overrideWithValue(FakeSessionStore(testSession())),
    personaRepositoryProvider.overrideWithValue(repository),
    onboardingCompletionStoreProvider.overrideWithValue(
      FakeOnboardingCompletionStore(),
    ),
  ],
  child: const MaterialApp(home: PersonaPage()),
);
