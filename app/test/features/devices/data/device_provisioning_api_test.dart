import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:echo_app/features/devices/data/device_provisioning_api.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses the firmware scan response', () async {
    final dio = Dio()
      ..httpClientAdapter = _Adapter((request) {
        expect(request.method, 'GET');
        expect(request.path, '/scan');
        return ResponseBody.fromString(
          jsonEncode(<String, dynamic>{
            'support_5g': false,
            'aps': <Map<String, dynamic>>[
              <String, dynamic>{'ssid': 'Home', 'rssi': -42, 'authmode': 3},
            ],
          }),
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
        );
      });

    final result = await DeviceProvisioningApi(dio: dio).scan();

    expect(result.supports5G, isFalse);
    expect(result.accessPoints.single.ssid, 'Home');
    expect(result.accessPoints.single.isOpen, isFalse);
  });

  test('submits credentials only to the local device endpoint', () async {
    late RequestOptions captured;
    final dio = Dio()
      ..httpClientAdapter = _Adapter((request) {
        captured = request;
        return ResponseBody.fromString(
          '{"success":true}',
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
        );
      });

    await DeviceProvisioningApi(
      dio: dio,
    ).submit(ssid: 'Home', password: 'secret');

    expect(captured.method, 'POST');
    expect(captured.path, '/submit');
    expect(captured.data, <String, String>{
      'ssid': 'Home',
      'password': 'secret',
    });
  });

  test('turns a failed firmware response into a user-facing error', () async {
    final dio = Dio()
      ..httpClientAdapter = _Adapter(
        (_) => ResponseBody.fromString(
          '{"success":false,"error":"bad password"}',
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
        ),
      );

    expect(
      () => DeviceProvisioningApi(
        dio: dio,
      ).submit(ssid: 'Home', password: 'wrong'),
      throwsA(isA<DeviceProvisioningException>()),
    );
  });

  test('exits firmware config mode after credentials are accepted', () async {
    late RequestOptions captured;
    final dio = Dio()
      ..httpClientAdapter = _Adapter((request) {
        captured = request;
        return ResponseBody.fromString(
          '{"success":true}',
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
        );
      });

    await DeviceProvisioningApi(dio: dio).exitConfigMode();

    expect(captured.method, 'POST');
    expect(captured.path, '/exit');
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
