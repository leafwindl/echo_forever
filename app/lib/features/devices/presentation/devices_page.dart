import 'package:echo_app/features/devices/domain/device.dart';
import 'package:echo_app/features/devices/presentation/device_ble_provisioning_page.dart';
import 'package:echo_app/features/devices/presentation/device_controller.dart';
import 'package:echo_app/features/devices/presentation/device_network_connection_dialog.dart';
import 'package:echo_app/features/devices/presentation/device_provisioning_page.dart';
import 'package:echo_app/features/devices/presentation/speaker_people_dialog.dart';
import 'package:echo_app/shared/widgets/echo_error_view.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class DevicesPage extends ConsumerWidget {
  const DevicesPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(deviceControllerProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('我的 Echo'),
        actions: [
          IconButton(
            tooltip: '刷新设备',
            onPressed: () =>
                ref.read(deviceControllerProvider.notifier).refresh(),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: state.when(
        loading: () => const EchoLoadingView(label: '正在加载设备'),
        error: (error, _) => EchoErrorView(
          message: '设备列表暂时无法加载',
          onRetry: () => ref.invalidate(deviceControllerProvider),
        ),
        data: (value) {
          if (value.devices.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('还没有绑定 Echo 设备'),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      onPressed: () async {
                        await Navigator.of(context).push<bool>(
                          MaterialPageRoute<bool>(
                            builder: (_) => const DeviceBleProvisioningPage(),
                          ),
                        );
                        if (context.mounted) {
                          await ref
                              .read(deviceControllerProvider.notifier)
                              .refresh();
                        }
                      },
                      icon: const Icon(Icons.wifi_tethering_rounded),
                      label: const Text('先为设备配网'),
                    ),
                  ],
                ),
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () =>
                ref.read(deviceControllerProvider.notifier).refresh(),
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
              itemCount: value.devices.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, index) =>
                  _DeviceTile(device: value.devices[index]),
            ),
          );
        },
      ),
    );
  }
}

class _DeviceTile extends ConsumerWidget {
  const _DeviceTile({required this.device});

  final EchoDevice device;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final color = device.isOnline
        ? Colors.green
        : Theme.of(context).colorScheme.outline;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      leading: CircleAvatar(
        backgroundColor: color.withValues(alpha: 0.12),
        child: Icon(Icons.speaker_rounded, color: color),
      ),
      title: Text(device.displayName),
      subtitle: Text(
        '${device.statusLabel} · 固件 ${device.firmwareVersion.isEmpty ? '未知' : device.firmwareVersion}',
      ),
      trailing: IconButton(
        tooltip: '设备设置',
        icon: const Icon(Icons.more_vert_rounded),
        onPressed: () => _showDeviceActions(context, ref),
      ),
    );
  }

  Future<void> _showDeviceActions(BuildContext context, WidgetRef ref) async {
    final controller = ref.read(deviceControllerProvider.notifier);
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: 0.92,
          child: ListView(
            padding: const EdgeInsets.only(bottom: 12),
            shrinkWrap: true,
            children: [
              ListTile(
                leading: const Icon(Icons.network_check_rounded),
                title: const Text('设备检测'),
                onTap: () => Navigator.pop(sheetContext, 'ble_connect'),
              ),
              ListTile(
                leading: const Icon(Icons.bluetooth_searching_rounded),
                title: const Text('蓝牙配网'),
                subtitle: const Text('扫描并连接 Echo BLE 设备'),
                onTap: () => Navigator.pop(sheetContext, 'ble_provision'),
              ),
              ListTile(
                leading: const Icon(Icons.wifi_tethering_rounded),
                title: const Text('重新配网'),
                subtitle: const Text('连接设备热点并设置家庭 Wi-Fi'),
                onTap: () => Navigator.pop(sheetContext, 'provision'),
              ),
              ListTile(
                leading: const Icon(Icons.edit_outlined),
                title: const Text('重命名'),
                onTap: () => Navigator.pop(sheetContext, 'rename'),
              ),
              ListTile(
                leading: const Icon(Icons.key_outlined),
                title: const Text('轮换设备凭证'),
                onTap: () => Navigator.pop(sheetContext, 'rotate'),
              ),
              ListTile(
                leading: const Icon(Icons.record_voice_over_rounded),
                title: const Text('人员声纹'),
                onTap: () => Navigator.pop(sheetContext, 'speaker'),
              ),
              ListTile(
                leading: const Icon(Icons.link_off_rounded),
                title: const Text('解绑设备'),
                onTap: () => Navigator.pop(sheetContext, 'unbind'),
              ),
            ],
          ),
        ),
      ),
    );
    if (!context.mounted) return;
    if (action == 'ble_connect') {
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => DeviceNetworkConnectionDialog(
          connect: () async {
            return controller.connectDevice(device.deviceId);
          },
        ),
      );
      if (context.mounted) {
        await controller.refresh();
      }
    } else if (action == 'ble_provision') {
      await Navigator.of(context).push<bool>(
        MaterialPageRoute<bool>(
          builder: (_) => const DeviceBleProvisioningPage(),
        ),
      );
      if (context.mounted) {
        await controller.refresh();
      }
    } else if (action == 'provision') {
      await Navigator.of(context).push<void>(
        MaterialPageRoute<void>(builder: (_) => const DeviceProvisioningPage()),
      );
    } else if (action == 'rename') {
      final nameController = TextEditingController(text: device.displayName);
      final name = await showDialog<String>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('重命名设备'),
          content: TextField(
            controller: nameController,
            autofocus: true,
            maxLength: 40,
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () =>
                  Navigator.pop(dialogContext, nameController.text.trim()),
              child: const Text('保存'),
            ),
          ],
        ),
      );
      nameController.dispose();
      if (name != null && name.isNotEmpty) {
        await controller.rename(device, name);
      }
    } else if (action == 'unbind') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('解绑设备？'),
          content: const Text('解绑后设备需要重新配对才能使用。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('解绑'),
            ),
          ],
        ),
      );
      if (confirmed == true) await controller.unbind(device);
    } else if (action == 'rotate') {
      final credential = await ref
          .read(deviceRepositoryProvider)
          .rotateCredential(device.deviceId);
      if (context.mounted) {
        await showDialog<void>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('新设备凭证'),
            content: SelectableText(credential.credential),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('完成'),
              ),
            ],
          ),
        );
      }
    } else if (action == 'speaker') {
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => SpeakerPeopleDialog(deviceId: device.deviceId),
      );
    }
  }
}
