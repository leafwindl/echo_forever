import 'package:echo_app/features/devices/data/device_provisioning_api.dart';
import 'package:echo_app/features/devices/data/device_wifi_bridge.dart';
import 'package:echo_app/features/devices/domain/provisioning_models.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

class DeviceProvisioningPage extends StatefulWidget {
  const DeviceProvisioningPage({super.key, this.api, this.wifiBridge});

  final DeviceProvisioningApi? api;
  final DeviceWifiBridge? wifiBridge;

  @override
  State<DeviceProvisioningPage> createState() => _DeviceProvisioningPageState();
}

class _DeviceProvisioningPageState extends State<DeviceProvisioningPage> {
  late final DeviceProvisioningApi _api = widget.api ?? DeviceProvisioningApi();
  late final DeviceWifiBridge _wifi =
      widget.wifiBridge ?? const DeviceWifiBridge();
  final _passwordController = TextEditingController();
  final _hotspotSsidController = TextEditingController(text: 'Xiaozhi-');
  List<ProvisioningAccessPoint> _accessPoints = const [];
  String? _selectedSsid;
  ProvisioningPhase _phase = ProvisioningPhase.idle;
  String? _error;
  bool _manualConnection = false;

  @override
  void dispose() {
    _passwordController.dispose();
    _hotspotSsidController.dispose();
    _wifi.disconnect();
    super.dispose();
  }

  Future<void> _connect() async {
    setState(() {
      _phase = ProvisioningPhase.connectingHotspot;
      _error = null;
      _manualConnection = false;
    });
    try {
      final hotspotSsid = _hotspotSsidController.text.trim();
      if (hotspotSsid.isEmpty || !hotspotSsid.startsWith('Xiaozhi-')) {
        throw const DeviceProvisioningException('请输入设备屏幕显示的完整 Xiaozhi-* 热点名称');
      }
      final connected = await _wifi.connectToHotspot(ssid: hotspotSsid);
      if (!connected) throw const DeviceProvisioningException('无法连接设备热点');
      await _scan();
    } on MissingPluginException {
      await _openManualConnection(
        '当前平台不支持自动切换 Wi-Fi，请在系统设置中连接 Xiaozhi-* 热点后返回。',
      );
    } on PlatformException catch (error) {
      await _openManualConnection(
        error.message ?? '请在系统设置中连接 Xiaozhi-* 热点后返回。',
      );
    } on Object catch (error) {
      setState(() {
        _phase = ProvisioningPhase.failure;
        _error = error.toString();
      });
    }
  }

  Future<void> _openManualConnection(String message) async {
    setState(() {
      _phase = ProvisioningPhase.idle;
      _manualConnection = true;
      _error = message;
    });
    try {
      await _wifi.openWifiSettings();
    } on MissingPluginException {
      // Keep the browser fallback available on platforms without the bridge.
    }
  }

  Future<void> _scan() async {
    setState(() {
      _phase = ProvisioningPhase.scanning;
      _error = null;
    });
    try {
      final result = await _api.scan();
      if (!mounted) return;
      setState(() {
        _accessPoints = result.accessPoints;
        _selectedSsid =
            _selectedSsid ??
            (result.accessPoints.isEmpty
                ? null
                : result.accessPoints.first.ssid);
        _phase = ProvisioningPhase.idle;
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _phase = ProvisioningPhase.failure;
        _error = '无法读取设备热点，请确认手机已连接 Xiaozhi-*：$error';
      });
    }
  }

  Future<void> _submit() async {
    final ssid = _selectedSsid;
    if (ssid == null || ssid.isEmpty) {
      setState(() => _error = '请选择一个 Wi-Fi 网络');
      return;
    }
    setState(() {
      _phase = ProvisioningPhase.submitting;
      _error = null;
    });
    try {
      await _api.submit(ssid: ssid, password: _passwordController.text);
      await _wifi.disconnect();
      if (!mounted) return;
      setState(() => _phase = ProvisioningPhase.success);
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _phase = ProvisioningPhase.failure;
        _error = error.toString();
      });
    }
  }

  Future<void> _openBrowserFallback() async {
    final uri = Uri.parse('http://192.168.4.1');
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) &&
        mounted) {
      setState(() => _error = '无法打开浏览器，请手动访问 192.168.4.1');
    }
  }

  bool get _busy =>
      _phase == ProvisioningPhase.connectingHotspot ||
      _phase == ProvisioningPhase.scanning ||
      _phase == ProvisioningPhase.submitting;

  @override
  Widget build(BuildContext context) {
    final success = _phase == ProvisioningPhase.success;
    return Scaffold(
      appBar: AppBar(title: const Text('Echo Wi-Fi 配网')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Icon(Icons.wifi_tethering_rounded, size: 56),
          const SizedBox(height: 12),
          Text(
            success ? '配网完成' : '把 Echo 连接到家庭 Wi-Fi',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          Text(
            success
                ? '设备会自动退出热点并连接 Echo 服务器。'
                : '手机需要先连接设备热点 Xiaozhi-*。Wi-Fi 密码只发送给设备，不会上传到 Echo 服务器。',
          ),
          const SizedBox(height: 24),
          if (_error != null) ...[
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: 12),
          ],
          if (!success) ...[
            TextField(
              controller: _hotspotSsidController,
              enabled: !_busy,
              decoration: const InputDecoration(
                labelText: '设备热点名称',
                hintText: '例如 Xiaozhi-342D',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _busy ? null : (_manualConnection ? _scan : _connect),
              icon: const Icon(Icons.wifi_find_rounded),
              label: Text(_manualConnection ? '已连接热点，重新扫描' : '连接设备热点'),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _busy ? null : _openBrowserFallback,
              icon: const Icon(Icons.open_in_browser_rounded),
              label: const Text('使用浏览器配网'),
            ),
            if (_accessPoints.isNotEmpty) ...[
              const SizedBox(height: 24),
              DropdownButtonFormField<String>(
                initialValue: _selectedSsid,
                decoration: const InputDecoration(
                  labelText: '家庭 Wi-Fi',
                  border: OutlineInputBorder(),
                ),
                items: _accessPoints
                    .map(
                      (ap) => DropdownMenuItem(
                        value: ap.ssid,
                        child: Text('${ap.ssid}  ${ap.rssi} dBm'),
                      ),
                    )
                    .toList(),
                onChanged: _busy
                    ? null
                    : (value) => setState(() => _selectedSsid = value),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _passwordController,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Wi-Fi 密码（开放网络可留空）',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _busy ? null : _submit,
                icon: const Icon(Icons.check_rounded),
                label: const Text('提交并连接'),
              ),
            ],
          ] else
            FilledButton.icon(
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.done_rounded),
              label: const Text('完成'),
            ),
          if (_busy) ...[
            const SizedBox(height: 20),
            const LinearProgressIndicator(),
          ],
        ],
      ),
    );
  }
}
