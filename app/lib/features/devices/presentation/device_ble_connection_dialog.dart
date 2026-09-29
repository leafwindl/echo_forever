import 'dart:async';

import 'package:echo_app/features/devices/data/device_ble_service.dart';
import 'package:echo_app/features/devices/data/device_blufi_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

class DeviceBleConnectionDialog extends StatefulWidget {
  const DeviceBleConnectionDialog({
    super.key,
    required this.deviceId,
    required this.verifyHardwareConnection,
  });

  final String deviceId;
  final Future<bool> Function() verifyHardwareConnection;

  @override
  State<DeviceBleConnectionDialog> createState() =>
      _DeviceBleConnectionDialogState();
}

class _DeviceBleConnectionDialogState extends State<DeviceBleConnectionDialog> {
  final DeviceBleService _ble = DeviceBleService();
  final DeviceBlufiService _blufi = DeviceBlufiService();
  StreamSubscription<DeviceBlufiEvent>? _events;
  String _status = '正在扫描已绑定 Echo';
  String? _error;
  bool _connected = false;
  bool _busy = true;
  bool _verificationStarted = false;

  @override
  void initState() {
    super.initState();
    unawaited(_connect());
  }

  @override
  void dispose() {
    unawaited(_events?.cancel());
    unawaited(_blufi.disconnect());
    super.dispose();
  }

  Future<void> _connect() async {
    try {
      final results = await _ble.scan();
      if (!mounted) return;
      final targetId = widget.deviceId.trim().toLowerCase();
      ScanResult? target;
      for (final result in results) {
        if (result.device.remoteId.str.toLowerCase() == targetId) {
          target = result;
          break;
        }
      }
      target ??= results.length == 1 ? results.first : null;
      if (target == null) {
        throw const DeviceBleException('未找到已绑定 Echo，请确认设备已开启蓝牙');
      }
      _events = _blufi.events.listen((event) {
        if (!mounted) return;
        if (event.state == 'failure') {
          setState(() {
            _busy = false;
            _status = '蓝牙连接失败';
            _error = event.message;
          });
          return;
        }
        setState(() {
          _status = event.state == 'ready'
              ? '蓝牙控制通道已连接，正在确认硬件上线'
              : event.message;
        });
        if ((event.state == 'ready' || event.state == 'success') &&
            !_verificationStarted) {
          _verificationStarted = true;
          unawaited(_verifyHardwareConnection());
        }
      });
      await _blufi.start(address: target.device.remoteId.str);
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = error.toString();
        _status = '连接失败';
      });
    }
  }

  Future<void> _verifyHardwareConnection() async {
    if (!mounted) return;
    setState(() {
      _status = '硬件正在连接 Echo 服务，请稍候';
    });
    try {
      final connected = await widget.verifyHardwareConnection();
      if (!mounted) return;
      setState(() {
        _busy = false;
        _connected = connected;
        _status = connected ? 'Echo 已连接，可开始使用' : '硬件尚未上线';
        if (!connected) {
          _error = '请确认 Echo 已连接家庭 Wi-Fi 并保持开机';
        }
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _status = '硬件连接验证失败';
        _error = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('一键连接'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              _connected
                  ? Icons.bluetooth_connected_rounded
                  : Icons.bluetooth_searching_rounded,
              size: 48,
              color: _connected ? Colors.green : colorScheme.primary,
            ),
            const SizedBox(height: 16),
            Text(_status),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: colorScheme.error)),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.pop(context),
          child: Text(_connected ? '完成' : '关闭'),
        ),
      ],
    );
  }
}
