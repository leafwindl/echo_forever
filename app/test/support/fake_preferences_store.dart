import 'package:echo_app/core/storage/preferences_store.dart';

class FakePreferencesStore implements PreferencesStore {
  FakePreferencesStore([Map<String, Object?>? initialValues])
    : _values = Map<String, Object?>.of(initialValues ?? <String, Object?>{});

  final Map<String, Object?> _values;

  @override
  Future<bool?> getBool(String key) async => _values[key] as bool?;

  @override
  Future<String?> getString(String key) async => _values[key] as String?;

  @override
  Future<void> remove(String key) async {
    _values.remove(key);
  }

  @override
  Future<void> setBool(String key, bool value) async {
    _values[key] = value;
  }

  @override
  Future<void> setString(String key, String value) async {
    _values[key] = value;
  }
}
