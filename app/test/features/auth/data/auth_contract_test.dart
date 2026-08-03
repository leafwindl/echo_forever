import 'package:echo_app/core/network/endpoints.dart';
import 'package:echo_app/features/auth/data/dto/auth_requests.dart';
import 'package:echo_app/features/auth/data/dto/auth_responses.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('uses the four M1 auth endpoints', () {
    expect(Endpoints.phoneLogin, '/login/phone');
    expect(Endpoints.verifyLogin, '/login/verify');
    expect(Endpoints.refreshLogin, '/login/refresh');
    expect(Endpoints.logout, '/login/logout');
  });

  test('serializes phone and verification requests as snake_case', () {
    expect(
      const PhoneLoginRequestDto(
        phone: '+8613800138000',
        deviceId: '76e8584a-1c97-43eb-a560-555eaabeaca9',
      ).toJson(),
      <String, Object?>{
        'phone': '+8613800138000',
        'device_id': '76e8584a-1c97-43eb-a560-555eaabeaca9',
        'purpose': 'login',
      },
    );
    expect(
      const VerifyLoginRequestDto(
        requestId: 'sms_request',
        phone: '+8613800138000',
        code: '482731',
        deviceId: '76e8584a-1c97-43eb-a560-555eaabeaca9',
      ).toJson()['request_id'],
      'sms_request',
    );
  });

  test('parses token rotation response', () {
    final response = TokenResponseDto.fromJson(<String, dynamic>{
      'user_id': 'phone_user',
      'access_token': 'access',
      'refresh_token': 'refresh',
      'token_type': 'bearer',
      'expires_in': 900,
      'refresh_expires_in': 2592000,
      'is_new_user': true,
    });

    expect(response.userId, 'phone_user');
    expect(response.expiresIn, 900);
    expect(response.refreshExpiresIn, 2592000);
    expect(response.isNewUser, isTrue);
  });
}
