import 'package:echo_app/core/storage/preferences_store.dart';
import 'package:echo_app/core/storage/storage_keys.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class OnboardingCompletionStore {
  const OnboardingCompletionStore(this._preferences);

  final PreferencesStore _preferences;

  String _key(String userId) =>
      '${StorageKeys.onboardingCompletedPrefix}.$userId';

  Future<bool> isCompleted(String userId) async {
    final completed = await _preferences.getBool(_key(userId));
    return completed ?? false;
  }

  Future<void> markCompleted(String userId) async {
    await _preferences.setBool(_key(userId), true);
  }

  Future<void> clear(String userId) async {
    await _preferences.remove(_key(userId));
  }
}

final onboardingCompletionStoreProvider = Provider<OnboardingCompletionStore>((
  ref,
) {
  return OnboardingCompletionStore(ref.watch(preferencesStoreProvider));
});
