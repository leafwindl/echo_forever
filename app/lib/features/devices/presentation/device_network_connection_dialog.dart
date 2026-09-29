import 'dart:async';

import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/errors/error_message_mapper.dart';
import 'package:flutter/material.dart';

class DeviceNetworkConnectionDialog extends StatefulWidget {
  const DeviceNetworkConnectionDialog({super.key, required this.connect});

  final Future<bool> Function() connect;

  @override
  State<DeviceNetworkConnectionDialog> createState() =>
      _DeviceNetworkConnectionDialogState();
}

class _DeviceNetworkConnectionDialogState
    extends State<DeviceNetworkConnectionDialog> {
  String _status = '正在等待硬件回应';
  String? _error;
  bool _connected = false;
  bool _busy = true;

  @override
  void initState() {
    super.initState();
    unawaited(_connect());
  }

  Future<void> _connect() async {
    try {
      final connected = await widget.connect();
      if (!mounted) return;
      setState(() {
        _busy = false;
        _connected = connected;
        _status = connected ? '检测通过，硬件已回应' : '未收到硬件回应';
        if (!connected) {
          _error = '硬件网络通道尚未建立，请确认 Echo 已联网后重试';
        }
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _status = '设备检测未通过';
        _error = error is AppException
            ? error.detail ?? ErrorMessageMapper.toChinese(error)
            : '未收到有效的硬件回执，请稍后重试';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('设备检测'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              _connected ? Icons.devices_other_rounded : Icons.sync_rounded,
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
