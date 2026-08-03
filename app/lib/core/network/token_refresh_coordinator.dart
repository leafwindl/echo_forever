import 'dart:async';

import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/errors/error_code.dart';

typedef ReadSession = SessionSnapshot? Function();
typedef RefreshSession =
    Future<SessionSnapshot> Function(String refreshToken, String deviceId);
typedef PersistSession = Future<void> Function(SessionSnapshot snapshot);
typedef ClearSession = Future<void> Function(String? serverCode);
typedef MarkSessionOffline = void Function();

class TokenRefreshCoordinator {
  TokenRefreshCoordinator({
    required this.readSession,
    required this.refreshSession,
    required this.persistSession,
    required this.clearSession,
    required this.markSessionOffline,
  });

  final ReadSession readSession;
  final RefreshSession refreshSession;
  final PersistSession persistSession;
  final ClearSession clearSession;
  final MarkSessionOffline markSessionOffline;
  Future<SessionSnapshot?>? _inFlight;

  Future<SessionSnapshot?> refresh({bool force = false}) {
    final active = _inFlight;
    if (active != null) {
      return active;
    }
    final future = _performRefresh(force: force);
    _inFlight = future;
    return future.whenComplete(() {
      if (identical(_inFlight, future)) {
        _inFlight = null;
      }
    });
  }

  Future<SessionSnapshot?> _performRefresh({required bool force}) async {
    final snapshot = readSession();
    if (snapshot == null || !snapshot.isAuthenticated) {
      return null;
    }
    if (!force && !snapshot.needsRefresh()) {
      return snapshot;
    }
    try {
      final refreshed = await refreshSession(
        snapshot.refreshToken!,
        snapshot.deviceId!,
      );
      await persistSession(refreshed);
      return refreshed;
    } on AppException catch (error) {
      if (_mustClearSession(error)) {
        await clearSession(error.serverCode);
      } else if (error.kind == AppExceptionKind.networkUnavailable ||
          error.kind == AppExceptionKind.timeout ||
          error.kind == AppExceptionKind.serviceUnavailable) {
        markSessionOffline();
      }
      rethrow;
    }
  }

  bool _mustClearSession(AppException error) {
    return error.serverCode == ErrorCode.refreshInvalid ||
        error.serverCode == ErrorCode.refreshExpired ||
        error.serverCode == ErrorCode.refreshReused ||
        error.serverCode == ErrorCode.userDisabled;
  }
}
