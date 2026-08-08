import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';

class PushApi {
  const PushApi(this._client);

  final DioClient _client;

  /// Registers the current account's Getui CID with Echo-backend.
  Future<void> registerToken({
    required String deviceId,
    required String platform,
    required String provider,
    required String token,
    required String appVersion,
    required String environment,
    required String locale,
  }) async {
    await _client.put<Map<String, dynamic>>(
      Endpoints.pushTokensMe,
      data: <String, dynamic>{
        'device_id': deviceId,
        'platform': platform,
        'provider': provider,
        'token': token,
        'app_version': appVersion,
        'environment': environment,
        'locale': locale,
      },
    );
  }

  /// Revokes the current device's push target during sign-out.
  Future<void> unregisterToken(String deviceId) {
    return _client.delete<void>(Endpoints.pushTokenForDevice(deviceId));
  }
}
