import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/chat/data/chat_providers.dart';
import 'package:echo_app/features/chat/presentation/chat_controller.dart';
import 'package:echo_app/features/persona/domain/persona.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../../chat/fakes.dart';
import '../fakes.dart';

void main() {
  test('loads persona and preserves local onboarding completion', () async {
    final repository = FakePersonaRepository(
      persona: personaFixture(onboardingCompleted: false),
    );
    final onboarding = FakeOnboardingCompletionStore()
      ..completedUsers.add('user-1');
    final container = _container(repository, onboarding: onboarding);
    addTearDown(container.dispose);

    await _loadSession(container);
    final state = await container.read(personaControllerProvider.future);

    expect(repository.getPersonaCalls, 1);
    expect(state.persona.onboardingCompleted, isTrue);
    expect(onboarding.markCompletedCalls, 1);
  });

  test(
    'updatePersona normalizes data and refreshes active chat name',
    () async {
      final repository = FakePersonaRepository(
        persona: personaFixture(preferredName: 'Old'),
      );
      final onboarding = FakeOnboardingCompletionStore();
      final container = _container(repository, onboarding: onboarding);
      addTearDown(container.dispose);
      await _loadSession(container);
      await container.read(personaControllerProvider.future);
      final chatSubscription = container.listen<ChatState>(
        chatControllerProvider,
        (_, _) {},
        fireImmediately: true,
      );
      addTearDown(chatSubscription.close);
      expect(container.read(chatControllerProvider).preferredName, 'Old');

      final persona = await container
          .read(personaControllerProvider.notifier)
          .updatePersona(
            const PersonaUpdate(
              preferredName: '  New  ',
              avoidTopics: <String>[' work ', 'Work', 'sleep'],
            ),
          );
      await container.pump();

      expect(persona?.preferredName, 'New');
      expect(repository.updates.single.preferredName, 'New');
      expect(repository.updates.single.avoidTopics, <String>['work', 'sleep']);
      expect(onboarding.completedUsers, contains('user-1'));
      expect(container.read(chatControllerProvider).preferredName, 'New');
      expect(
        container.read(chatControllerProvider).messages.single.content,
        contains('New'),
      );
    },
  );

  test('resetRelationship invalidates relationship state provider', () async {
    final repository = FakePersonaRepository(
      relationship: relationshipFixture(stage: 'close', stageLabel: 'Close'),
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    await container.read(personaControllerProvider.future);
    final relationshipSubscription = container.listen(
      relationshipStateProvider,
      (_, _) {},
      fireImmediately: true,
    );
    addTearDown(relationshipSubscription.close);
    final initial = await container.read(relationshipStateProvider.future);
    expect(initial.stage, 'close');

    final reset = await container
        .read(personaControllerProvider.notifier)
        .resetRelationship();
    await container.pump();
    final refreshed = await container.read(relationshipStateProvider.future);

    expect(reset?.stage, 'new');
    expect(refreshed.stage, 'new');
    expect(repository.resetRelationshipCalls, 1);
    expect(repository.getRelationshipCalls, 2);
  });
}

ProviderContainer _container(
  FakePersonaRepository repository, {
  FakeOnboardingCompletionStore? onboarding,
}) {
  return ProviderContainer(
    overrides: [
      secureStoreProvider.overrideWithValue(FakeSessionStore(testSession())),
      personaRepositoryProvider.overrideWithValue(repository),
      onboardingCompletionStoreProvider.overrideWithValue(
        onboarding ?? FakeOnboardingCompletionStore(),
      ),
      chatRepositoryProvider.overrideWithValue(FakeChatRepository()),
    ],
  );
}

Future<void> _loadSession(ProviderContainer container) async {
  await container.read(sessionControllerProvider.future);
  await container.pump();
}
