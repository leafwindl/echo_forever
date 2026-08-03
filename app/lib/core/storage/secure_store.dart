import 'dart:convert';

import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/storage/storage_keys.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

abstract interface class SessionStore {
  Future<void> clearSession();
  Future<String> getOrCreateDeviceId();
  Future<SessionSnapshot> readSession();
  Future<void> writeSession(SessionSnapshot snapshot);
}

class SecureStore implements SessionStore {
  SecureStore(this._storage, {this.uuid = const Uuid()});

  final FlutterSecureStorage _storage;
  final Uuid uuid;

  @override
  Future<SessionSnapshot> readSession() async {
    final encoded = await _storage.read(key: StorageKeys.authSession);
    if (encoded == null || encoded.isEmpty) {
      return const SessionSnapshot.signedOut();
    }
    try {
      final json = jsonDecode(encoded) as Map<String, dynamic>;
      return SessionSnapshot.fromJson(json);
    } on Object {
      await clearSession();
      return const SessionSnapshot.signedOut();
    }
  }

  @override
  Future<void> writeSession(SessionSnapshot snapshot) async {
    if (!snapshot.isAuthenticated) {
      throw ArgumentError.value(snapshot, 'snapshot', 'must be authenticated');
    }
    // The complete token pair is persisted as one secure-storage value. A
    // partially updated access/refresh pair is therefore never observable.
    await _storage.write(
      key: StorageKeys.authSession,
      value: jsonEncode(snapshot.toJson()),
    );
  }

  @override
  Future<void> clearSession() {
    return _storage.delete(key: StorageKeys.authSession);
  }

  @override
  Future<String> getOrCreateDeviceId() async {
    final existing = await _storage.read(key: StorageKeys.deviceId);
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }
    final value = uuid.v4();
    await _storage.write(key: StorageKeys.deviceId, value: value);
    return value;
  }
}

final secureStoreProvider = Provider<SessionStore>((ref) {
  return SecureStore(const FlutterSecureStorage());
});
