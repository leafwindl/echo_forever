import 'package:dio/dio.dart';
import 'package:echo_app/features/devices/domain/provisioning_models.dart';

class DeviceProvisioningApi {
  DeviceProvisioningApi({Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: 'http://192.168.4.1',
              connectTimeout: const Duration(seconds: 5),
              sendTimeout: const Duration(seconds: 5),
              receiveTimeout: const Duration(seconds: 35),
              contentType: Headers.jsonContentType,
              responseType: ResponseType.json,
            ),
          );

  final Dio _dio;

  Future<ProvisioningScanResult> scan() async {
    final response = await _dio.get<Map<String, dynamic>>('/scan');
    return ProvisioningScanResult.fromJson(
      response.data ?? const <String, dynamic>{},
    );
  }

  Future<void> submit({required String ssid, required String password}) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/submit',
      data: <String, String>{'ssid': ssid, 'password': password},
      options: Options(contentType: Headers.jsonContentType),
    );
    final body = response.data ?? const <String, dynamic>{};
    if (body['success'] != true) {
      throw DeviceProvisioningException(
        body['error'] as String? ?? '设备连接 Wi-Fi 失败',
      );
    }
  }

  Future<void> exitConfigMode() async {
    final response = await _dio.post<Map<String, dynamic>>('/exit');
    final body = response.data ?? const <String, dynamic>{};
    if (body['success'] != true) {
      throw DeviceProvisioningException(
        body['error'] as String? ?? '设备无法退出配网模式',
      );
    }
  }
}

class DeviceProvisioningException implements Exception {
  const DeviceProvisioningException(this.message);

  final String message;

  @override
  String toString() => message;
}
