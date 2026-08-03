import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

class PreferencesStore {
  PreferencesStore(this._preferences);

  final SharedPreferencesAsync _preferences;

  Future<String?> getString(String key) => _preferences.getString(key);

  Future<void> remove(String key) => _preferences.remove(key);

  Future<void> setString(String key, String value) =>
      _preferences.setString(key, value);
}

final preferencesStoreProvider = Provider<PreferencesStore>((ref) {
  return PreferencesStore(SharedPreferencesAsync());
});
