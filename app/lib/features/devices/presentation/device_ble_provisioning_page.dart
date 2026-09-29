import 'dart:async';

import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/errors/error_message_mapper.dart';
import 'package:echo_app/features/devices/data/device_ble_service.dart';
import 'package:echo_app/features/devices/data/device_blufi_service.dart';
import 'package:echo_app/features/devices/domain/device.dart';
import 'package:echo_app/features/devices/presentation/device_controller.dart';
import 'package:echo_app/features/devices/presentation/device_provisioning_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class DeviceBleProvisioningPage extends ConsumerStatefulWidget {
  const DeviceBleProvisioningPage({super.key, this.targetDeviceId});

  final String? targetDeviceId;

  @override
  ConsumerState<DeviceBleProvisioningPage> createState() =>
      _DeviceBleProvisioningPageState();
}

class _DeviceBleProvisioningPageState
    extends ConsumerState<DeviceBleProvisioningPage> {
  final DeviceBleService _ble = DeviceBleService();
  final DeviceBlufiService _blufi = DeviceBlufiService();
  final Map<String, ScanResult> _devices = <String, ScanResult>{};
  final TextEditingController _wifiSsidController = TextEditingController();
  final TextEditingController _wifiPasswordController = TextEditingController();
  final TextEditingController _pairingIdController = TextEditingController();
  final TextEditingController _pairingCodeController = TextEditingController();

  StreamSubscription<DeviceBlufiEvent>? _blufiSubscription;
  ScanResult? _selectedDevice;
  String? _error;
  String? _status;
  String? _blufiState;
  Set<String> _deviceIdsBeforeProvisioning = <String>{};
  bool _protocolReady = false;
  bool _scanning = false;
  bool _connecting = false;
  bool _submitting = false;
  bool _claiming = false;
  bool _claimed = false;
  bool _showPairingFallback = false;
  bool _wifiConnectUnconfirmed = false;

  bool get _connectOnly => widget.targetDeviceId?.trim().isNotEmpty == true;

  bool get _hasSession =>
      _selectedDevice != null && _blufiState != 'disconnected';

  bool get _busy => _scanning || _connecting || _submitting || _claiming;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_scan);
  }

  @override
  void dispose() {
    final subscription = _blufiSubscription;
    if (subscription != null) {
      unawaited(subscription.cancel());
    }
    unawaited(_blufi.disconnect());
    _wifiSsidController.dispose();
    _wifiPasswordController.dispose();
    _pairingIdController.dispose();
    _pairingCodeController.dispose();
    super.dispose();
  }

  Future<void> _scan() async {
    if (_busy || _hasSession) return;
    setState(() {
      _scanning = true;
      _error = null;
      _status = '正在扫描附近的 Echo';
      _devices.clear();
    });
    try {
      final results = await _ble.scan();
      if (!mounted) return;
      setState(() {
        for (final result in results) {
          _devices[result.device.remoteId.str] = result;
        }
        _status = _devices.isEmpty
            ? '没有发现 Echo'
            : '发现 ${_devices.length} 台 Echo';
      });
      if (_connectOnly && mounted) {
        final targetId = widget.targetDeviceId!.trim().toLowerCase();
        ScanResult? target;
        for (final result in _devices.values) {
          if (result.device.remoteId.str.toLowerCase() == targetId) {
            target = result;
            break;
          }
        }
        target ??= _devices.length == 1 ? _devices.values.first : null;
        if (target != null) await _connect(target);
      }
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _status = null;
      });
    } finally {
      if (mounted) setState(() => _scanning = false);
    }
  }

  Future<void> _connect(ScanResult result) async {
    if (_busy || _hasSession) return;
    await _blufiSubscription?.cancel();
    if (!mounted) return;
    setState(() {
      _selectedDevice = result;
      _connecting = true;
      _protocolReady = false;
      _claimed = false;
      _showPairingFallback = false;
      _wifiConnectUnconfirmed = false;
      _blufiState = 'connecting';
      _error = null;
      _status = '正在连接 ${_deviceName(result)}';
    });

    _blufiSubscription = _blufi.events.listen(
      _handleBlufiEvent,
      onError: _handleBlufiStreamError,
    );
    try {
      await _blufi.start(address: result.device.remoteId.str);
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _connecting = false;
        _blufiState = 'failure';
        _error = 'BluFi 连接失败：$error';
        _status = null;
      });
    }
  }

  void _handleBlufiEvent(DeviceBlufiEvent event) {
    if (!mounted) return;
    debugPrint(
      'Echo BLE event state=${event.state} messageLength=${event.message.length}',
    );
    var shouldPollBinding = false;
    var shouldCloseConnection = false;
    setState(() {
      _blufiState = event.state;
      _status = event.message;
      switch (event.state) {
        case 'connecting':
        case 'connected':
        case 'negotiating_security':
          _connecting = true;
        case 'ready':
          _connecting = false;
          _submitting = false;
          if (_connectOnly) {
            _protocolReady = false;
            _claimed = true;
            _blufiState = 'success';
            _status = 'Echo 已连接，无需重新配对';
            shouldCloseConnection = true;
          } else {
            _protocolReady = true;
          }
        case 'binding':
        case 'configuring':
        case 'wifi_connecting':
          _connecting = false;
          _submitting = true;
          _protocolReady = true;
        case 'success':
          _connecting = false;
          _submitting = false;
          _protocolReady = false;
          _wifiConnectUnconfirmed = false;
          _error = null;
          if (_connectOnly) {
            _claimed = true;
            _status = 'Echo 已连接，无需重新配对';
          } else {
            shouldPollBinding = !_claimed && !_claiming;
          }
        case 'wifi_failed':
          _connecting = false;
          _submitting = false;
          _protocolReady = false;
          _wifiConnectUnconfirmed = true;
          _error = null;
          _status = '${event.message}，正在检查设备是否已上线';
          shouldPollBinding = !_claimed && !_claiming;
        case 'failure':
          _connecting = false;
          _submitting = false;
          _claiming = false;
          _error = event.message;
        case 'disconnected':
          _connecting = false;
          _submitting = false;
          _protocolReady = false;
        default:
          break;
      }
    });
    if (shouldPollBinding) {
      unawaited(_waitForDirectBinding());
    }
    if (shouldCloseConnection) {
      unawaited(_closeAfterConnection());
    }
  }

  Future<void> _closeAfterConnection() async {
    await Future<void>.delayed(const Duration(milliseconds: 700));
    if (mounted) Navigator.of(context).pop(true);
  }

  void _handleBlufiStreamError(Object error, StackTrace stackTrace) {
    if (!mounted) return;
    setState(() {
      _connecting = false;
      _submitting = false;
      _claiming = false;
      _blufiState = 'failure';
      _error = 'BluFi 状态通道失败：$error';
    });
  }

  Future<void> _submitWifi() async {
    if (_connectOnly) return;
    final ssid = _wifiSsidController.text.trim();
    if (ssid.isEmpty) {
      setState(() => _error = '请输入家庭 Wi-Fi 名称');
      return;
    }
    if (!_protocolReady) {
      setState(() => _error = '蓝牙配网通道尚未就绪，请重新连接 Echo');
      return;
    }

    final currentDevices =
        ref.read(deviceControllerProvider).asData?.value.devices ??
        const <EchoDevice>[];
    final knownIds = currentDevices
        .map((device) => device.deviceId)
        .where((deviceId) => deviceId.isNotEmpty)
        .toSet();

    setState(() {
      _submitting = true;
      _claimed = false;
      _showPairingFallback = false;
      _wifiConnectUnconfirmed = false;
      _deviceIdsBeforeProvisioning = knownIds;
      _error = null;
      _status = '正在创建设备绑定会话';
    });
    try {
      final session = await ref
          .read(deviceRepositoryProvider)
          .createProvisioningSession();
      debugPrint(
        'Echo BLE provisioning session created tokenLength=${session.claimToken.length}',
      );
      if (session.claimToken.isEmpty) {
        throw StateError('设备绑定会话为空');
      }
      if (!mounted) return;
      setState(() {
        _status = '正在通过 BluFi 发送 Wi-Fi 配置';
      });
      await _blufi.configure(
        ssid: ssid,
        password: _wifiPasswordController.text,
        claimToken: session.claimToken,
      );
    } on Object catch (error) {
      if (!mounted) return;
      final detail = error is AppException
          ? error.detail ?? ErrorMessageMapper.toChinese(error)
          : error.toString();
      setState(() {
        _submitting = false;
        _error = '发送 Wi-Fi 配置失败：$detail';
      });
    }
  }

  Future<void> _waitForDirectBinding() async {
    if (!mounted) return;
    setState(() {
      _claiming = true;
      _showPairingFallback = false;
      _status = _wifiConnectUnconfirmed
          ? '正在检查 Echo 是否已完成联网'
          : 'Echo 已连接 Wi-Fi，正在写入我的 Echo';
    });

    for (var attempt = 0; attempt < 24; attempt += 1) {
      await Future<void>.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      await ref.read(deviceControllerProvider.notifier).refresh();
      if (!mounted) return;
      final devices =
          ref.read(deviceControllerProvider).asData?.value.devices ??
          const <EchoDevice>[];
      debugPrint(
        'Echo BLE binding poll attempt=${attempt + 1} devices=${devices.length}',
      );
      if (_containsProvisionedDevice(devices)) {
        setState(() {
          _claiming = false;
          _claimed = true;
          _showPairingFallback = false;
          _status = '设备已绑定到当前账号';
        });
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (mounted) Navigator.of(context).pop(true);
        return;
      }
    }

    if (!mounted) return;
    setState(() {
      _claiming = false;
      _showPairingFallback = true;
      if (_wifiConnectUnconfirmed) {
        _error = '设备没有确认连上 Wi-Fi，也暂时没有出现在设备列表；请确认使用 2.4GHz Wi-Fi 且密码正确。';
        _status = '配网未完成';
      } else {
        _status = 'Wi-Fi 已配置，暂时还没在设备列表看到它';
      }
    });
  }

  bool _containsProvisionedDevice(List<EchoDevice> devices) {
    if (devices.isEmpty) return false;
    if (_deviceIdsBeforeProvisioning.isEmpty) return true;
    for (final device in devices) {
      if (device.deviceId.isNotEmpty &&
          !_deviceIdsBeforeProvisioning.contains(device.deviceId)) {
        return true;
      }
    }
    return false;
  }

  Future<void> _disconnect() async {
    await _blufiSubscription?.cancel();
    _blufiSubscription = null;
    try {
      await _blufi.disconnect();
    } catch (_) {
      // The native bridge may already have been torn down by Android.
    }
    if (!mounted) return;
    setState(() {
      _selectedDevice = null;
      _blufiState = 'disconnected';
      _protocolReady = false;
      _connecting = false;
      _submitting = false;
      _claiming = false;
      _showPairingFallback = false;
      _wifiConnectUnconfirmed = false;
      _status = '已断开 Echo';
    });
  }

  Future<void> _claimDevice() async {
    final code = _pairingCodeController.text.trim();
    if (!RegExp(r'^\d{6}$').hasMatch(code)) {
      setState(() => _error = '请输入设备屏幕上的 6 位配对码');
      return;
    }

    setState(() {
      _claiming = true;
      _error = null;
    });
    try {
      await ref
          .read(deviceRepositoryProvider)
          .claimPairing(
            pairingId: _pairingIdController.text.trim(),
            code: code,
          );
      await ref.read(deviceControllerProvider.notifier).refresh();
      if (!mounted) return;
      setState(() {
        _claiming = false;
        _claimed = true;
        _showPairingFallback = false;
        _status = '设备已绑定到当前账号';
      });
      await Future<void>.delayed(const Duration(milliseconds: 250));
      if (mounted) Navigator.of(context).pop(true);
    } on Object catch (error) {
      if (!mounted) return;
      final detail = error is AppException
          ? error.detail ?? ErrorMessageMapper.toChinese(error)
          : error.toString();
      setState(() {
        _claiming = false;
        _error = '绑定设备失败：$detail';
      });
    }
  }

  String _deviceName(ScanResult result) {
    final advertisedName = result.advertisementData.advName.trim();
    if (advertisedName.isNotEmpty) return advertisedName;
    final platformName = result.device.platformName.trim();
    return platformName.isNotEmpty ? platformName : DeviceBleService.deviceName;
  }

  @override
  Widget build(BuildContext context) {
    final connected = _hasSession && _blufiState != 'success';
    final showWifiForm = connected && _protocolReady;
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Echo 蓝牙配网')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
        children: [
          const Icon(Icons.bluetooth_searching_rounded, size: 56),
          const SizedBox(height: 12),
          Text(
            '通过 BluFi 配置 Wi-Fi',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 20),
          if (_error != null) ...[
            Text(_error!, style: TextStyle(color: colorScheme.error)),
            const SizedBox(height: 12),
          ],
          if (_status != null)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                connected
                    ? Icons.bluetooth_connected_rounded
                    : Icons.bluetooth_rounded,
                color: connected ? colorScheme.primary : null,
              ),
              title: Text(_status!),
              subtitle: connected && _selectedDevice != null
                  ? Text(_deviceName(_selectedDevice!))
                  : null,
            ),
          if (showWifiForm && !_connectOnly) ...[
            const SizedBox(height: 8),
            TextField(
              controller: _wifiSsidController,
              enabled: !_submitting,
              textInputAction: TextInputAction.next,
              decoration: const InputDecoration(
                labelText: '家庭 Wi-Fi 名称',
                prefixIcon: Icon(Icons.wifi_rounded),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _wifiPasswordController,
              enabled: !_submitting,
              obscureText: true,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _submitWifi(),
              decoration: const InputDecoration(
                labelText: '家庭 Wi-Fi 密码',
                prefixIcon: Icon(Icons.lock_outline_rounded),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _submitting ? null : _submitWifi,
              icon: const Icon(Icons.send_rounded),
              label: Text(_submitting ? '正在配置...' : '发送 Wi-Fi 配置'),
            ),
          ],
          if (_blufiState == 'success') ...[
            const SizedBox(height: 12),
            Text(
              _connectOnly
                  ? 'Echo 已连接，无需重新配对'
                  : _claimed
                  ? 'Echo 已出现在我的设备中'
                  : _claiming
                  ? '正在刷新设备列表'
                  : 'Echo 已连接家庭 Wi-Fi',
              style: TextStyle(color: colorScheme.primary),
            ),
            if (_showPairingFallback && !_claimed) ...[
              const SizedBox(height: 12),
              TextField(
                controller: _pairingIdController,
                enabled: !_claiming,
                decoration: const InputDecoration(
                  labelText: '配对会话 ID（可选）',
                  prefixIcon: Icon(Icons.link_rounded),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _pairingCodeController,
                enabled: !_claiming,
                keyboardType: TextInputType.number,
                maxLength: 6,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _claimDevice(),
                decoration: const InputDecoration(
                  labelText: '设备 6 位配对码',
                  prefixIcon: Icon(Icons.password_rounded),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 4),
              FilledButton.icon(
                onPressed: _claiming ? null : _claimDevice,
                icon: const Icon(Icons.add_link_rounded),
                label: Text(_claiming ? '正在绑定...' : '绑定到当前账号'),
              ),
            ],
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _busy || _hasSession ? null : _scan,
            icon: const Icon(Icons.refresh_rounded),
            label: Text(_scanning ? '扫描中...' : '扫描 Echo'),
          ),
          if (connected || _blufiState == 'success') ...[
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _busy ? null : _disconnect,
              icon: const Icon(Icons.bluetooth_disabled_rounded),
              label: const Text('断开蓝牙'),
            ),
          ],
          const SizedBox(height: 20),
          if (_devices.isEmpty && !_scanning)
            const Center(child: Text('请让 Echo 进入 BLE 配网模式后重新扫描'))
          else
            ..._devices.values.map(
              (result) => Card(
                child: ListTile(
                  leading: const Icon(Icons.speaker_rounded),
                  title: Text(_deviceName(result)),
                  subtitle: Text(result.device.remoteId.str),
                  trailing: _selectedDevice?.device == result.device
                      ? const Icon(
                          Icons.check_circle_rounded,
                          color: Colors.green,
                        )
                      : TextButton(
                          onPressed: _busy || _hasSession
                              ? null
                              : () => _connect(result),
                          child: const Text('连接'),
                        ),
                ),
              ),
            ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: () => Navigator.of(context).push<void>(
              MaterialPageRoute<void>(
                builder: (_) => const DeviceProvisioningPage(),
              ),
            ),
            icon: const Icon(Icons.wifi_tethering_rounded),
            label: const Text('使用网页热点配网（备用）'),
          ),
        ],
      ),
    );
  }
}
