import 'dart:async';
import 'dart:io';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:permission_handler/permission_handler.dart';

class DeviceBleService {
  static const String deviceName = 'Xiaozhi-Blufi';
  static const String legacyDeviceName = 'BLUFI_DEVICE';
  static const String blufiServiceUuid = '0000ffff-0000-1000-8000-00805f9b34fb';

  Future<void> requestPermissions() async {
    if (!Platform.isAndroid) return;

    final permissions = <Permission>[
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
    ];
    if (await _androidNeedsLocationPermission()) {
      permissions.add(Permission.locationWhenInUse);
    }
    final result = await permissions.request();
    if (result.values.any((status) => status.isPermanentlyDenied)) {
      throw const DeviceBleException('蓝牙权限已被永久拒绝，请在系统设置中允许 Echo 使用附近的设备');
    }
    if (result.values.any((status) => status.isDenied)) {
      throw const DeviceBleException('需要允许 Echo 使用蓝牙，才能扫描 Echo 设备');
    }
  }

  Future<bool> _androidNeedsLocationPermission() async {
    // Android 12+ uses BLUETOOTH_SCAN/CONNECT. Older Android versions need
    // location permission for BLE discovery.
    if (!Platform.isAndroid) return false;
    return !(await Permission.bluetoothScan.isGranted);
  }

  Future<void> ensureBluetoothReady() async {
    if (!await FlutterBluePlus.isSupported) {
      throw const DeviceBleException('当前手机不支持低功耗蓝牙');
    }
    if (Platform.isAndroid) {
      await FlutterBluePlus.turnOn();
    }
    final state = await FlutterBluePlus.adapterState
        .where((value) => value != BluetoothAdapterState.unknown)
        .first
        .timeout(
          const Duration(seconds: 5),
          onTimeout: () => BluetoothAdapterState.unknown,
        );
    if (state != BluetoothAdapterState.on) {
      throw const DeviceBleException('请打开手机蓝牙后重试');
    }
  }

  Future<List<ScanResult>> scan({
    Duration timeout = const Duration(seconds: 12),
  }) async {
    await requestPermissions();
    await ensureBluetoothReady();

    final resultsById = <String, ScanResult>{};
    final subscription = FlutterBluePlus.onScanResults.listen(
      (results) {
        for (final result in results) {
          if (isEchoDevice(result)) {
            resultsById[result.device.remoteId.str] = result;
          }
        }
      },
      onError: (Object error) {
        // The await below surfaces platform scan failures. This callback only
        // prevents an uncaught stream error from terminating the page.
      },
    );
    try {
      await FlutterBluePlus.startScan(timeout: timeout);
      await FlutterBluePlus.isScanning
          .where((scanning) => !scanning)
          .first
          .timeout(timeout + const Duration(seconds: 2));
    } finally {
      await subscription.cancel();
      if (await FlutterBluePlus.isScanning.first) {
        await FlutterBluePlus.stopScan();
      }
    }
    return resultsById.values.toList(growable: false);
  }

  bool isEchoDevice(ScanResult result) {
    final advertisedName = result.advertisementData.advName.trim();
    final platformName = result.device.platformName.trim();
    return _isBlufiName(advertisedName) || _isBlufiName(platformName);
  }

  bool _isBlufiName(String name) {
    return name == deviceName ||
        name == legacyDeviceName ||
        name.startsWith('$deviceName-') ||
        name.startsWith('$legacyDeviceName-');
  }

  Future<int> connect(BluetoothDevice device) async {
    await device.connect(
      license: License.nonprofit,
      timeout: const Duration(seconds: 15),
      autoConnect: false,
    );
    final services = await device.discoverServices();
    return services.length;
  }

  Future<void> disconnect(BluetoothDevice device) async {
    if (device.isConnected) {
      await device.disconnect();
    }
  }
}

class DeviceBleException implements Exception {
  const DeviceBleException(this.message);

  final String message;

  @override
  String toString() => message;
}
