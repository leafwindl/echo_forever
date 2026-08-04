import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';

class PushApi {
  const PushApi(this._client);

  final DioClient _client;

  /// TODO(M5b): Echo-backend does not currently expose this endpoint.
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

  /// TODO(M5b): wire this when the backend DELETE contract is available.
  Future<void> unregisterToken(String deviceId) {
    return _client.delete<void>(Endpoints.pushTokenForDevice(deviceId));
  }
}
