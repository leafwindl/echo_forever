import 'dart:async';

import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/errors/error_code.dart';
import 'package:echo_app/core/network/token_refresh_coordinator.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  SessionSnapshot session({String accessToken = 'old-access'}) {
    return SessionSnapshot.authenticated(
      userId: 'phone_user',
      accessToken: accessToken,
      refreshToken: 'refresh',
      tokenType: 'bearer',
      accessExpiresAt: DateTime.now().toUtc().add(const Duration(minutes: 1)),
      refreshExpiresAt: DateTime.now().toUtc().add(const Duration(days: 30)),
      deviceId: 'device-id',
    );
  }

  test('coalesces concurrent refresh calls into one request', () async {
    final gate = Completer<void>();
    final original = session();
    var refreshCalls = 0;
    var persistCalls = 0;
    final coordinator = TokenRefreshCoordinator(
      readSession: () => original,
      refreshSession: (refreshToken, deviceId) async {
        refreshCalls += 1;
        await gate.future;
        return session(accessToken: 'new-access');
      },
      persistSession: (_) async => persistCalls += 1,
      clearSession: (_) async {},
      markSessionOffline: () {},
    );

    final first = coordinator.refresh(force: true);
    final second = coordinator.refresh(force: true);
    expect(refreshCalls, 1);
    gate.complete();

    final results = await Future.wait(<Future<SessionSnapshot?>>[
      first,
      second,
    ]);
    expect(
      results.map((value) => value?.accessToken),
      everyElement('new-access'),
    );
    expect(refreshCalls, 1);
    expect(persistCalls, 1);
  });

  test('clears the session when a rotated refresh token is reused', () async {
    final original = session();
    String? clearedForCode;
    final coordinator = TokenRefreshCoordinator(
      readSession: () => original,
      refreshSession: (_, _) async => throw const AppException(
        kind: AppExceptionKind.unauthorized,
        serverCode: ErrorCode.refreshReused,
      ),
      persistSession: (_) async {},
      clearSession: (serverCode) async => clearedForCode = serverCode,
      markSessionOffline: () {},
    );

    await expectLater(
      coordinator.refresh(force: true),
      throwsA(isA<AppException>()),
    );
    expect(clearedForCode, ErrorCode.refreshReused);
  });
}
