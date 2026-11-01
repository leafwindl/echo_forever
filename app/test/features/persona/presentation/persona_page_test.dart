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
  testWidgets('shows the relationship result without internal permission', (
    tester,
  ) async {
    final repository = FakePersonaRepository(
      relationship: RelationshipStateDto(
        relationshipType: 'friend',
        relationshipTypeLabel: '朋友',
        stage: 'familiar',
        stageLabel: '熟悉',
        interactionTurns: 12,
        activeDays: 3,
        affectionPermission: 'welcomed',
        schemaVersion: 1,
      ),
    );
    await tester.pumpWidget(_page(repository));
    await tester.pumpAndSettle();

    expect(find.text('关于她'), findsOneWidget);
    expect(find.text('朋友'), findsOneWidget);
    expect(find.text('12 次'), findsOneWidget);
    expect(find.text('3 天'), findsOneWidget);
    expect(find.textContaining('welcomed'), findsNothing);
    expect(find.text('AI 恋人'), findsNothing);
  });

  testWidgets('opens the confirmation window and accepts the proposal', (
    tester,
  ) async {
    final repository = FakePersonaRepository(
      relationship: RelationshipStateDto(
        relationshipType: 'acquaintance',
        relationshipTypeLabel: '初识',
        stage: 'familiar',
        stageLabel: '熟悉',
        interactionTurns: 4,
        activeDays: 4,
        affectionPermission: 'unknown',
        schemaVersion: 1,
        pendingProposal: const RelationshipProposalDto(
          proposalId: 'proposal-1',
          direction: 'friend',
          directionLabel: '朋友',
          status: 'pending',
        ),
      ),
    );
    await tester.pumpWidget(_page(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('查看确认窗口'));
    await tester.pumpAndSettle();
    expect(find.textContaining('做朋友吗'), findsOneWidget);

    await tester.tap(find.text('愿意'));
    await tester.pumpAndSettle();
    expect(repository.acceptedProposalId, 'proposal-1');
    expect(find.text('朋友'), findsWidgets);
  });

  testWidgets('defers from the confirmation window without changing relation', (
    tester,
  ) async {
    final repository = FakePersonaRepository(
      relationship: RelationshipStateDto(
        relationshipType: 'acquaintance',
        relationshipTypeLabel: '初识',
        stage: 'familiar',
        stageLabel: '熟悉',
        interactionTurns: 4,
        activeDays: 4,
        affectionPermission: 'unknown',
        schemaVersion: 1,
        pendingProposal: const RelationshipProposalDto(
          proposalId: 'proposal-2',
          direction: 'friend',
          directionLabel: '朋友',
          status: 'pending',
        ),
      ),
    );
    await tester.pumpWidget(_page(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('查看确认窗口'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('再想想'));
    await tester.pumpAndSettle();

    expect(repository.deferredProposalId, 'proposal-2');
    expect(repository.relationship.relationshipTypeLabel, '初识');
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
