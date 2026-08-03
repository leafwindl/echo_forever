import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';
import 'package:echo_app/features/auth/data/dto/auth_requests.dart';
import 'package:echo_app/features/auth/data/dto/auth_responses.dart';

class AuthApi {
  const AuthApi(this._publicClient, this._authenticatedClient);

  final DioClient _publicClient;
  final DioClient _authenticatedClient;

  Future<PhoneLoginResponseDto> requestPhoneCode(
    PhoneLoginRequestDto request,
  ) async {
    final response = await _publicClient.post<Map<String, dynamic>>(
      Endpoints.phoneLogin,
      data: request.toJson(),
    );
    return PhoneLoginResponseDto.fromJson(response.data!);
  }

  Future<TokenResponseDto> verifyCode(VerifyLoginRequestDto request) async {
    final response = await _publicClient.post<Map<String, dynamic>>(
      Endpoints.verifyLogin,
      data: request.toJson(),
    );
    return TokenResponseDto.fromJson(response.data!);
  }

  Future<TokenResponseDto> refresh(RefreshLoginRequestDto request) async {
    final response = await _publicClient.post<Map<String, dynamic>>(
      Endpoints.refreshLogin,
      data: request.toJson(),
    );
    return TokenResponseDto.fromJson(response.data!);
  }

  Future<void> logout(RefreshLoginRequestDto request) async {
    await _authenticatedClient.post<void>(
      Endpoints.logout,
      data: request.toJson(),
    );
  }
}
