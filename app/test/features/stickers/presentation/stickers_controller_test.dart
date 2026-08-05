import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';
import 'package:echo_app/features/stickers/presentation/stickers_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  test('loads stickers for an authenticated user', () async {
    final repository = FakeStickersRepository(
      items: <StickerItem>[stickerFixture(description: 'wave')],
    );
    final container = _container(repository);
    addTearDown(container.dispose);

    await _loadSession(container);
    final state = await container.read(stickersControllerProvider.future);

    expect(state.items.single.description, 'wave');
    expect(repository.listCalls, 1);
  });

  test('rejects unsupported formats before uploading', () async {
    final repository = FakeStickersRepository();
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await container.read(stickersControllerProvider.future);

    final saved = await container
        .read(stickersControllerProvider.notifier)
        .savePickedImage(
          const StickerUploadSelection(
            path: '/tmp/wave.bmp',
            name: 'wave.bmp',
            byteLength: 100,
          ),
          description: '挥手',
          tags: const <String>['挥手'],
        );

    final state = container.read(stickersControllerProvider).asData!.value;
    expect(saved, isFalse);
    expect(repository.uploadCalls, 0);
    expect(state.saveStep, StickerSaveStep.failed);
    expect(state.error?.detail, contains('PNG'));
  });

  test('uploads, confirms, and refreshes the sticker list', () async {
    final repository = FakeStickersRepository(items: <StickerItem>[]);
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await container.read(stickersControllerProvider.future);

    final saved = await container
        .read(stickersControllerProvider.notifier)
        .savePickedImage(
          const StickerUploadSelection(
            path: '/tmp/wave.png',
            name: 'wave.png',
            byteLength: 100,
          ),
          description: '开心挥手',
          tags: const <String>['开心', '挥手'],
        );

    final state = container.read(stickersControllerProvider).asData!.value;
    expect(saved, isTrue);
    expect(repository.uploadedNames, <String>['wave.png']);
    expect(repository.uploadedDescriptions, <String>['开心挥手']);
    expect(repository.uploadedTags, <List<String>>[
      <String>['开心', '挥手'],
    ]);
    expect(repository.confirmedIds, <String>['uploaded-1']);
    expect(state.saveStep, StickerSaveStep.idle);
    expect(state.items.single.stickerId, 'uploaded-1');
  });

  test('retries confirm-save without re-uploading', () async {
    final repository = FakeStickersRepository(items: <StickerItem>[]);
    var failConfirm = true;
    repository.onConfirm = (stickerId) async {
      if (failConfirm) {
        failConfirm = false;
        throw const AppException(kind: AppExceptionKind.serviceUnavailable);
      }
      final confirmed = stickerFixture(stickerId: stickerId);
      repository.items = <StickerItem>[confirmed];
      return confirmed;
    };
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await container.read(stickersControllerProvider.future);

    final first = await container
        .read(stickersControllerProvider.notifier)
        .savePickedImage(
          const StickerUploadSelection(
            path: '/tmp/wave.png',
            name: 'wave.png',
            byteLength: 100,
          ),
          description: '开心挥手',
          tags: const <String>['开心', '挥手'],
        );
    final failed = container.read(stickersControllerProvider).asData!.value;
    final retry = await container
        .read(stickersControllerProvider.notifier)
        .retrySavePending();

    expect(first, isFalse);
    expect(failed.saveStep, StickerSaveStep.failed);
    expect(failed.uploadedSticker?.stickerId, 'uploaded-1');
    expect(retry, isTrue);
    expect(repository.uploadCalls, 1);
    expect(repository.confirmCalls, 2);
  });

  test('deletes only user-owned stickers', () async {
    final repository = FakeStickersRepository(
      items: <StickerItem>[
        stickerFixture(stickerId: 'user-sticker'),
        stickerFixture(
          stickerId: 'echo-sticker',
          ownerType: StickerOwnerType.echo,
          source: StickerSource.builtin,
        ),
      ],
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    final state = await container.read(stickersControllerProvider.future);

    final rejected = await container
        .read(stickersControllerProvider.notifier)
        .deleteSticker(state.items.last);
    final deleted = await container
        .read(stickersControllerProvider.notifier)
        .deleteSticker(state.items.first);

    expect(rejected, isFalse);
    expect(deleted, isTrue);
    expect(repository.deletedIds, <String>['user-sticker']);
  });
}

ProviderContainer _container(FakeStickersRepository repository) {
  return ProviderContainer(
    overrides: [
      secureStoreProvider.overrideWithValue(FakeSessionStore(testSession())),
      stickersRepositoryProvider.overrideWithValue(repository),
    ],
  );
}

ProviderSubscription<AsyncValue<StickersState>> _keepAlive(
  ProviderContainer container,
) {
  return container.listen<AsyncValue<StickersState>>(
    stickersControllerProvider,
    (_, _) {},
    fireImmediately: true,
  );
}

Future<void> _loadSession(ProviderContainer container) async {
  await container.read(sessionControllerProvider.future);
  await container.pump();
}
