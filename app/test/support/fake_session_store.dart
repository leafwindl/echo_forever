import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/storage/secure_store.dart';

class FakeSessionStore implements SessionStore {
  FakeSessionStore(this.snapshot);

  SessionSnapshot snapshot;
  int clearCalls = 0;
  int writeCalls = 0;

  @override
  Future<void> clearSession() async {
    clearCalls += 1;
    snapshot = const SessionSnapshot.signedOut();
  }

  @override
  Future<String> getOrCreateDeviceId() async =>
      snapshot.deviceId ?? 'device-id';

  @override
  Future<SessionSnapshot> readSession() async => snapshot;

  @override
  Future<void> writeSession(SessionSnapshot snapshot) async {
    writeCalls += 1;
    this.snapshot = snapshot;
  }
}

SessionSnapshot testSession({String userId = 'user-1'}) {
  return SessionSnapshot.authenticated(
    userId: userId,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    tokenType: 'bearer',
    accessExpiresAt: DateTime.utc(2026, 8, 4, 8).add(const Duration(hours: 1)),
    refreshExpiresAt: DateTime.utc(2026, 8, 4, 8).add(const Duration(days: 30)),
    deviceId: 'device-id',
  );
}
