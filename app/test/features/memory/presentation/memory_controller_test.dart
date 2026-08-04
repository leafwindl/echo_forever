import 'dart:async';

import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/memory/domain/memory.dart';
import 'package:echo_app/features/memory/presentation/memory_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  test('loads active memories for an authenticated user', () async {
    final repository = FakeMemoryRepository(
      activeMemories: <MemoryRecord>[memoryFixture(content: 'likes tea')],
    );
    final container = _container(repository);
    addTearDown(container.dispose);

    await _loadSession(container);
    final state = await container.read(memoryControllerProvider.future);

    expect(state.tab, MemoryTab.active);
    expect(state.memories.single.content, 'likes tea');
    expect(repository.listedStatuses, <MemoryStatus>[MemoryStatus.active]);
    expect(repository.listedLimits, <int>[100]);
  });

  test('switchTab fetches deleted memories', () async {
    final repository = FakeMemoryRepository(
      deletedMemories: <MemoryRecord>[
        memoryFixture(
          memoryId: 'mem-deleted',
          content: 'deleted memory',
          status: MemoryStatus.deleted,
        ),
      ],
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await container.read(memoryControllerProvider.future);

    final next = await container
        .read(memoryControllerProvider.notifier)
        .switchTab(MemoryTab.deleted);

    expect(next?.tab, MemoryTab.deleted);
    expect(next?.memories.single.memoryId, 'mem-deleted');
    expect(repository.listedStatuses, <MemoryStatus>[
      MemoryStatus.active,
      MemoryStatus.deleted,
    ]);
  });

  test(
    'deleteMemory exposes deletingId and refreshes the active list',
    () async {
      final gate = Completer<MemoryDeleteResult>();
      final repository = FakeMemoryRepository();
      repository.onDeleteMemory = (memoryId) => gate.future;
      final container = _container(repository);
      addTearDown(container.dispose);
      await _loadSession(container);
      final subscription = _keepAlive(container);
      addTearDown(subscription.close);
      await container.read(memoryControllerProvider.future);

      final deletion = container
          .read(memoryControllerProvider.notifier)
          .deleteMemory('mem-1');
      expect(
        container.read(memoryControllerProvider).asData?.value.deletingId,
        'mem-1',
      );

      repository.activeMemories = <MemoryRecord>[];
      gate.complete(
        const MemoryDeleteResult(
          memoryId: 'mem-1',
          status: MemoryStatus.deleted,
        ),
      );

      expect(await deletion, isTrue);
      final state = container.read(memoryControllerProvider).asData!.value;
      expect(state.deletingId, isNull);
      expect(state.memories, isEmpty);
      expect(repository.deletedIds, <String>['mem-1']);
    },
  );

  test('clearMemories clears active list and returns backend count', () async {
    final repository = FakeMemoryRepository(
      activeMemories: <MemoryRecord>[
        memoryFixture(memoryId: 'mem-1'),
        memoryFixture(memoryId: 'mem-2'),
      ],
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    await _loadSession(container);
    final subscription = _keepAlive(container);
    addTearDown(subscription.close);
    await container.read(memoryControllerProvider.future);

    final cleared = await container
        .read(memoryControllerProvider.notifier)
        .clearMemories();

    expect(cleared, 2);
    expect(repository.clearCalls, 1);
    expect(
      container.read(memoryControllerProvider).asData?.value.memories,
      isEmpty,
    );
  });
}

ProviderContainer _container(FakeMemoryRepository repository) {
  return ProviderContainer(
    overrides: [
      secureStoreProvider.overrideWithValue(FakeSessionStore(testSession())),
      memoryRepositoryProvider.overrideWithValue(repository),
    ],
  );
}

ProviderSubscription<AsyncValue<MemoryState>> _keepAlive(
  ProviderContainer container,
) {
  return container.listen<AsyncValue<MemoryState>>(
    memoryControllerProvider,
    (_, _) {},
    fireImmediately: true,
  );
}

Future<void> _loadSession(ProviderContainer container) async {
  await container.read(sessionControllerProvider.future);
  await container.pump();
}
