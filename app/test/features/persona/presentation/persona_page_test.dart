import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/domain/persona.dart';
import 'package:echo_app/features/persona/presentation/persona_page.dart';
import 'package:echo_app/shared/widgets/primary_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  testWidgets(
    'relationship choice saves independently and internal permission is not shown',
    (tester) async {
      final repository = FakePersonaRepository(
        persona: personaFixture(),
        relationship: const RelationshipStateDto.initial(),
      );
      await tester.pumpWidget(_page(repository));
      await tester.pumpAndSettle();
      expect(find.text('和 Echo 的关系'), findsOneWidget);
      expect(find.text('熟悉程度 · 初识'), findsOneWidget);
      expect(find.textContaining('unknown'), findsNothing);
      await tester.tap(find.text('AI 恋人'));
      await tester.pumpAndSettle();
      expect(repository.updatedRelationshipMode, RelationshipMode.aiPartner);
      expect(repository.relationship.stage, 'new');
      expect(repository.updates, isEmpty);
      expect(
        tester
            .widget<SegmentedButton<RelationshipMode>>(
              find.byType(SegmentedButton<RelationshipMode>),
            )
            .selected,
        <RelationshipMode>{RelationshipMode.aiPartner},
      );
    },
  );

  testWidgets('failed relationship update keeps the saved selection', (
    tester,
  ) async {
    final repository = FakePersonaRepository(
      persona: personaFixture(),
      relationship: const RelationshipStateDto.initial(),
    )..updateRelationshipModeError = StateError('offline');
    await tester.pumpWidget(_page(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.text('AI 恋人'));
    await tester.pumpAndSettle();
    expect(repository.updatedRelationshipMode, isNull);
    expect(
      tester
          .widget<SegmentedButton<RelationshipMode>>(
            find.byType(SegmentedButton<RelationshipMode>),
          )
          .selected,
      <RelationshipMode>{RelationshipMode.friend},
    );
    expect(find.byType(SnackBar), findsOneWidget);
  });

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
