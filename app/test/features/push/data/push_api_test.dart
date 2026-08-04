import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/push/data/push_api.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('registerToken sends the documented PUT contract', () async {
    late RequestOptions captured;
    final dio = Dio()
      ..httpClientAdapter = _Adapter((request) {
        captured = request;
        return ResponseBody.fromString(
          jsonEncode(<String, String>{'registered_at': '2026-08-04T00:00:00Z'}),
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
        );
      });
    final api = PushApi(DioClient(dio));

    await api.registerToken(
      deviceId: 'device-1',
      platform: 'android',
      provider: 'fcm',
      token: 'secret-token',
      appVersion: '2.0.0',
      environment: 'production',
      locale: 'zh-CN',
    );

    expect(captured.method, 'PUT');
    expect(captured.path, '/push/tokens/me');
    expect(captured.data, <String, dynamic>{
      'device_id': 'device-1',
      'platform': 'android',
      'provider': 'fcm',
      'token': 'secret-token',
      'app_version': '2.0.0',
      'environment': 'production',
      'locale': 'zh-CN',
    });
  });
}

class _Adapter implements HttpClientAdapter {
  _Adapter(this.handler);
  final ResponseBody Function(RequestOptions request) handler;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async => handler(options);

  @override
  void close({bool force = false}) {}
}
