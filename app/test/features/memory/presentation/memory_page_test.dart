import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/memory/domain/memory.dart';
import 'package:echo_app/features/memory/presentation/memory_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  testWidgets('confirms delete and refreshes the visible memory list', (
    tester,
  ) async {
    final repository = FakeMemoryRepository(
      activeMemories: <MemoryRecord>[
        memoryFixture(content: 'prefers quiet mornings'),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          secureStoreProvider.overrideWithValue(
            FakeSessionStore(testSession()),
          ),
          memoryRepositoryProvider.overrideWithValue(repository),
        ],
        child: const MaterialApp(home: MemoryPage()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('prefers quiet mornings'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.delete_outline_rounded).last);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FilledButton).last);
    await tester.pumpAndSettle();

    expect(repository.deletedIds, <String>['mem-1']);
    expect(find.text('prefers quiet mornings'), findsNothing);
  });
}
