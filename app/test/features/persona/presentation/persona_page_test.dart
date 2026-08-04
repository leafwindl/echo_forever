import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/persona/presentation/persona_page.dart';
import 'package:echo_app/shared/widgets/primary_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  testWidgets('saves edited persona through the controller', (tester) async {
    final repository = FakePersonaRepository(
      persona: personaFixture(preferredName: 'Old'),
      relationship: relationshipFixture(),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          secureStoreProvider.overrideWithValue(
            FakeSessionStore(testSession()),
          ),
          personaRepositoryProvider.overrideWithValue(repository),
          onboardingCompletionStoreProvider.overrideWithValue(
            FakeOnboardingCompletionStore(),
          ),
        ],
        child: const MaterialApp(home: PersonaPage()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField).first, 'New');
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

    expect(repository.updates.single.preferredName, 'New');
    expect(repository.persona.preferredName, 'New');
  });
}
