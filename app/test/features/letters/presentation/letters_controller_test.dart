import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/letters/domain/letter.dart';
import 'package:echo_app/features/letters/presentation/letters_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  test('loads letters and exposes unread_count', () async {
    final repository = FakeLettersRepository(
      letters: <DailyLetter>[
        letterFixture(letterId: 'unread'),
        letterFixture(letterId: 'read', status: LetterStatus.read),
      ],
    );
    final container = _container(repository);
    addTearDown(container.dispose);

    await _loadSession(container);
    final state = await container.read(lettersControllerProvider.future);

    expect(state.letters, hasLength(2));
    expect(state.unreadCount, 1);
    expect(container.read(lettersUnreadCountProvider), 1);
  });

  test('opening an unread letter fetches detail and marks it read', () async {
    final repository = FakeLettersRepository(
      letters: <DailyLetter>[letterFixture(content: 'full letter')],
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await container.read(lettersControllerProvider.future);

    final opened = await container
        .read(lettersControllerProvider.notifier)
        .openLetter('letter-1');

    final state = container.read(lettersControllerProvider).asData!.value;
    expect(opened, isTrue);
    expect(repository.fetchedIds, <String>['letter-1']);
    expect(repository.readIds, <String>['letter-1']);
    expect(state.selected?.status, LetterStatus.read);
    expect(state.unreadCount, 0);
    expect(container.read(lettersUnreadCountProvider), 0);
  });

  test('keeps unread state when mark-read fails and can retry', () async {
    final repository = FakeLettersRepository();
    repository.readError = const AppException(
      kind: AppExceptionKind.networkUnavailable,
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await container.read(lettersControllerProvider.future);

    final opened = await container
        .read(lettersControllerProvider.notifier)
        .openLetter('letter-1');
    var state = container.read(lettersControllerProvider).asData!.value;
    expect(opened, isTrue);
    expect(state.selected?.status, LetterStatus.ready);
    expect(state.unreadCount, 1);
    expect(state.error?.kind, AppExceptionKind.networkUnavailable);

    repository.readError = null;
    final retried = await container
        .read(lettersControllerProvider.notifier)
        .markSelectedRead();
    state = container.read(lettersControllerProvider).asData!.value;
    expect(retried, isTrue);
    expect(repository.readCalls, 2);
    expect(state.selected?.status, LetterStatus.read);
    expect(state.unreadCount, 0);
  });
}

ProviderContainer _container(FakeLettersRepository repository) {
  return ProviderContainer(
    overrides: [
      secureStoreProvider.overrideWithValue(FakeSessionStore(testSession())),
      lettersRepositoryProvider.overrideWithValue(repository),
    ],
  );
}

ProviderSubscription<AsyncValue<LettersState>> _keepAlive(
  ProviderContainer container,
) {
  return container.listen<AsyncValue<LettersState>>(
    lettersControllerProvider,
    (_, _) {},
    fireImmediately: true,
  );
}

Future<void> _loadSession(ProviderContainer container) async {
  await container.read(sessionControllerProvider.future);
  await container.pump();
}
