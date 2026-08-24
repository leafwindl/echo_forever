import 'package:flutter/services.dart';

class DeviceWifiBridge {
  const DeviceWifiBridge();

  static const _channel = MethodChannel('echo/device_wifi');

  Future<bool> connectToHotspot({required String ssid}) async {
    final result = await _channel.invokeMethod<bool>(
      'connectToHotspot',
      <String, Object?>{'ssid': ssid},
    );
    return result == true;
  }

  Future<void> disconnect() async {
    await _channel.invokeMethod<void>('disconnect');
  }

  Future<void> openWifiSettings() async {
    await _channel.invokeMethod<void>('openWifiSettings');
  }
}
