import 'package:echo_app/features/push/data/getui_push_gateway.dart';
import 'package:echo_app/features/push/data/push_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

class NotificationSettingsPage extends ConsumerWidget {
  const NotificationSettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(pushControllerProvider);
    final status = state.permission;
    final enabled = state.isEnabled;
    final needsSystemSettings =
        status == PushPermissionStatus.denied || enabled;
    return Scaffold(
      appBar: AppBar(title: const Text('通知设置')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: <Widget>[
          const Text(
            '通知只用于提醒 Echo 来信等与你的账号相关的事件。锁屏通知不会包含聊天正文、Persona、记忆或转写内容。你可以随时在系统设置中关闭通知。',
          ),
          const SizedBox(height: 20),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Echo 通知'),
            subtitle: Text(_statusLabel(status)),
            trailing: FilledButton.icon(
              onPressed: needsSystemSettings
                  ? _openSystemSettings
                  : () => ref
                        .read(pushControllerProvider.notifier)
                        .requestPermission(),
              icon: Icon(
                enabled
                    ? Icons.settings_outlined
                    : Icons.notifications_active_outlined,
              ),
              label: Text(needsSystemSettings ? '系统设置' : '允许通知'),
            ),
          ),
          if (state.error != null) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              state.error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
    );
  }

  String _statusLabel(PushPermissionStatus status) => switch (status) {
    PushPermissionStatus.authorized => '已允许',
    PushPermissionStatus.denied => '已拒绝，可前往系统设置修改',
    PushPermissionStatus.unsupported => '当前设备暂不支持',
    PushPermissionStatus.unknown => '尚未设置',
  };

  Future<void> _openSystemSettings() async {
    await openAppSettings();
  }
}
