import 'package:echo_app/features/auth/domain/auth_session.dart';
import 'package:echo_app/features/auth/domain/phone_verification.dart';

abstract interface class AuthRepository {
  Future<PhoneVerification> requestPhoneCode(String phone);

  Future<AuthSession> verifyCode({
    required PhoneVerification verification,
    required String code,
  });

  Future<AuthSession> refresh({
    required String refreshToken,
    required String deviceId,
  });

  Future<void> logout({required String refreshToken, required String deviceId});
}
