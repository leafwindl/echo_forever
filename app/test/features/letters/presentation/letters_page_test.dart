import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/letters/domain/letter.dart';
import 'package:echo_app/features/letters/presentation/letters_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  testWidgets('opens a letter dialog and marks unread letters read', (
    tester,
  ) async {
    final repository = FakeLettersRepository(
      letters: <DailyLetter>[letterFixture(content: 'full letter content')],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          secureStoreProvider.overrideWithValue(
            FakeSessionStore(testSession()),
          ),
          lettersRepositoryProvider.overrideWithValue(repository),
        ],
        child: const MaterialApp(home: LettersPage()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('写给你的信'));
    await tester.pumpAndSettle();

    expect(repository.fetchedIds, <String>['letter-1']);
    expect(repository.readIds, <String>['letter-1']);
    expect(
      find.widgetWithText(SelectableText, 'full letter content'),
      findsOneWidget,
    );
    expect(find.text('Echo 来信 (0)'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, '收好这封信'), findsOneWidget);
  });
}
