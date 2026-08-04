import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_preferences_store.dart';

void main() {
  test('stores completion per user and defaults to false', () async {
    final store = OnboardingCompletionStore(FakePreferencesStore());

    expect(await store.isCompleted('user-1'), isFalse);

    await store.markCompleted('user-1');

    expect(await store.isCompleted('user-1'), isTrue);
    expect(await store.isCompleted('user-2'), isFalse);

    await store.clear('user-1');

    expect(await store.isCompleted('user-1'), isFalse);
  });
}
