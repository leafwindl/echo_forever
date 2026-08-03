import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/auth_session/session_events.dart';
import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/routing/pending_route_store.dart';
import 'package:echo_app/features/auth/domain/auth_session.dart';
import 'package:echo_app/features/auth/domain/phone_verification.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AuthOperation { idle, sendingCode, verifyingCode, signingOut }

class AuthFlowState {
  const AuthFlowState({
    this.operation = AuthOperation.idle,
    this.verification,
    this.error,
  });

  final AuthOperation operation;
  final PhoneVerification? verification;
  final AppException? error;

  bool get isBusy => operation != AuthOperation.idle;

  AuthFlowState copyWith({
    AuthOperation? operation,
    PhoneVerification? verification,
    bool clearVerification = false,
    AppException? error,
    bool clearError = false,
  }) {
    return AuthFlowState(
      operation: operation ?? this.operation,
      verification: clearVerification
          ? null
          : verification ?? this.verification,
      error: clearError ? null : error ?? this.error,
    );
  }
}

class AuthController extends Notifier<AuthFlowState> {
  @override
  AuthFlowState build() => const AuthFlowState();

  Future<PhoneVerification?> requestCode(String phone) async {
    if (state.isBusy) {
      return null;
    }
    state = state.copyWith(
      operation: AuthOperation.sendingCode,
      clearError: true,
    );
    try {
      final verification = await ref
          .read(authRepositoryProvider)
          .requestPhoneCode(phone);
      state = AuthFlowState(verification: verification);
      return verification;
    } on Object catch (error) {
      state = state.copyWith(
        operation: AuthOperation.idle,
        error: _asAppException(error),
      );
      return null;
    }
  }

  Future<bool> verifyCode({
    required PhoneVerification verification,
    required String code,
  }) async {
    if (state.isBusy) {
      return false;
    }
    state = state.copyWith(
      operation: AuthOperation.verifyingCode,
      verification: verification,
      clearError: true,
    );
    try {
      final session = await ref
          .read(authRepositoryProvider)
          .verifyCode(verification: verification, code: code);
      await ref
          .read(sessionControllerProvider.notifier)
          .establish(_toSnapshot(session));
      state = const AuthFlowState();
      return true;
    } on Object catch (error) {
      state = state.copyWith(
        operation: AuthOperation.idle,
        error: _asAppException(error),
      );
      return false;
    }
  }

  Future<void> logout() async {
    if (state.isBusy) {
      return;
    }
    state = state.copyWith(
      operation: AuthOperation.signingOut,
      clearError: true,
    );
    final snapshot = ref.read(sessionControllerProvider).asData?.value;
    try {
      if (snapshot?.isAuthenticated ?? false) {
        await ref
            .read(authRepositoryProvider)
            .logout(
              refreshToken: snapshot!.refreshToken!,
              deviceId: snapshot.deviceId!,
            );
      }
    } on Object {
      // Local sign-out must complete even when remote revocation is unavailable.
    } finally {
      ref.read(pendingRouteStoreProvider.notifier).clear();
      await ref
          .read(sessionControllerProvider.notifier)
          .signOut(SessionEndReason.userLogout);
      state = const AuthFlowState();
    }
  }

  void resetVerification() {
    state = const AuthFlowState();
  }

  AppException _asAppException(Object error) {
    return error is AppException
        ? error
        : const AppException(kind: AppExceptionKind.unexpected);
  }

  SessionSnapshot _toSnapshot(AuthSession session) {
    return SessionSnapshot.authenticated(
      userId: session.userId,
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
      tokenType: session.tokenType,
      accessExpiresAt: session.accessExpiresAt,
      refreshExpiresAt: session.refreshExpiresAt,
      deviceId: session.deviceId,
    );
  }
}

final authControllerProvider = NotifierProvider<AuthController, AuthFlowState>(
  AuthController.new,
);
