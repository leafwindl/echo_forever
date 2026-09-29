import 'package:flutter/services.dart';

class DeviceBlufiEvent {
  const DeviceBlufiEvent({
    required this.state,
    required this.message,
    this.ssid,
  });

  factory DeviceBlufiEvent.fromPlatform(Object? value) {
    if (value is! Map) {
      throw const FormatException('BluFi 状态数据格式错误');
    }
    final map = Map<Object?, Object?>.from(value);
    return DeviceBlufiEvent(
      state: map['state'] as String? ?? 'unknown',
      message: map['message'] as String? ?? '',
      ssid: map['ssid'] as String?,
    );
  }

  final String state;
  final String message;
  final String? ssid;
}

class DeviceBlufiService {
  static const _channel = MethodChannel('echo/device_blufi');
  static const _eventsChannel = EventChannel('echo/device_blufi/events');

  Stream<DeviceBlufiEvent> get events => _eventsChannel
      .receiveBroadcastStream()
      .map(DeviceBlufiEvent.fromPlatform);

  Future<void> start({required String address}) {
    return _channel.invokeMethod<void>('start', <String, Object?>{
      'address': address,
    });
  }

  Future<void> configure({
    required String ssid,
    required String password,
    String claimToken = '',
  }) {
    return _channel.invokeMethod<void>('configure', <String, Object?>{
      'ssid': ssid,
      'password': password,
      'claimToken': claimToken,
    });
  }

  Future<void> disconnect() {
    return _channel.invokeMethod<void>('disconnect');
  }
}
