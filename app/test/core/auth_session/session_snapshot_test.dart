import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('round-trips an authenticated session as one record', () {
    final snapshot = SessionSnapshot.authenticated(
      userId: 'phone_user',
      accessToken: 'access',
      refreshToken: 'refresh',
      tokenType: 'bearer',
      accessExpiresAt: DateTime.utc(2030, 1, 1),
      refreshExpiresAt: DateTime.utc(2030, 2, 1),
      deviceId: 'device-id',
    );

    final restored = SessionSnapshot.fromJson(snapshot.toJson());

    expect(restored.isAuthenticated, isTrue);
    expect(restored.accessToken, 'access');
    expect(restored.refreshToken, 'refresh');
    expect(restored.deviceId, 'device-id');
  });

  test('detects access tokens inside the refresh safety window', () {
    final snapshot = SessionSnapshot.authenticated(
      userId: 'phone_user',
      accessToken: 'access',
      refreshToken: 'refresh',
      tokenType: 'bearer',
      accessExpiresAt: DateTime.utc(2030, 1, 1, 0, 1),
      refreshExpiresAt: DateTime.utc(2030, 2, 1),
      deviceId: 'device-id',
    );

    expect(snapshot.needsRefresh(now: DateTime.utc(2030, 1, 1)), isTrue);
  });
}
