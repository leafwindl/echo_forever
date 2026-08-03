import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/auth/data/auth_api.dart';
import 'package:echo_app/features/auth/data/dto/auth_requests.dart';
import 'package:echo_app/features/auth/data/dto/auth_responses.dart';
import 'package:echo_app/features/auth/domain/auth_repository.dart';
import 'package:echo_app/features/auth/domain/auth_session.dart';
import 'package:echo_app/features/auth/domain/phone_verification.dart';

class AuthRepositoryImpl implements AuthRepository {
  const AuthRepositoryImpl(this._api, this._secureStore);

  final AuthApi _api;
  final SessionStore _secureStore;

  @override
  Future<PhoneVerification> requestPhoneCode(String phone) async {
    final deviceId = await _secureStore.getOrCreateDeviceId();
    final response = await _api.requestPhoneCode(
      PhoneLoginRequestDto(phone: phone, deviceId: deviceId),
    );
    final now = DateTime.now().toUtc();
    return PhoneVerification(
      requestId: response.requestId,
      phone: phone,
      phoneMasked: response.phoneMasked,
      expiresAt: now.add(Duration(seconds: response.expiresIn)),
      resendAt: now.add(Duration(seconds: response.resendAfter)),
    );
  }

  @override
  Future<AuthSession> verifyCode({
    required PhoneVerification verification,
    required String code,
  }) async {
    final deviceId = await _secureStore.getOrCreateDeviceId();
    final response = await _api.verifyCode(
      VerifyLoginRequestDto(
        requestId: verification.requestId,
        phone: verification.phone,
        code: code,
        deviceId: deviceId,
      ),
    );
    return _toSession(response, deviceId);
  }

  @override
  Future<AuthSession> refresh({
    required String refreshToken,
    required String deviceId,
  }) async {
    final response = await _api.refresh(
      RefreshLoginRequestDto(refreshToken: refreshToken, deviceId: deviceId),
    );
    return _toSession(response, deviceId);
  }

  @override
  Future<void> logout({
    required String refreshToken,
    required String deviceId,
  }) {
    return _api.logout(
      RefreshLoginRequestDto(refreshToken: refreshToken, deviceId: deviceId),
    );
  }

  AuthSession _toSession(TokenResponseDto response, String deviceId) {
    final now = DateTime.now().toUtc();
    return AuthSession(
      userId: response.userId,
      accessToken: response.accessToken,
      refreshToken: response.refreshToken,
      tokenType: response.tokenType,
      accessExpiresAt: now.add(Duration(seconds: response.expiresIn)),
      refreshExpiresAt: now.add(Duration(seconds: response.refreshExpiresIn)),
      deviceId: deviceId,
      isNewUser: response.isNewUser,
    );
  }
}
