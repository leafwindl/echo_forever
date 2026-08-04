import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

abstract interface class PreferencesStore {
  Future<bool?> getBool(String key);
  Future<String?> getString(String key);
  Future<void> remove(String key);
  Future<void> setBool(String key, bool value);
  Future<void> setString(String key, String value);
}

class SharedPreferencesStore implements PreferencesStore {
  SharedPreferencesStore(this._preferences);

  final SharedPreferencesAsync _preferences;

  @override
  Future<bool?> getBool(String key) => _preferences.getBool(key);

  @override
  Future<String?> getString(String key) => _preferences.getString(key);

  @override
  Future<void> remove(String key) => _preferences.remove(key);

  @override
  Future<void> setBool(String key, bool value) =>
      _preferences.setBool(key, value);

  @override
  Future<void> setString(String key, String value) =>
      _preferences.setString(key, value);
}

final preferencesStoreProvider = Provider<PreferencesStore>((ref) {
  return SharedPreferencesStore(SharedPreferencesAsync());
});
