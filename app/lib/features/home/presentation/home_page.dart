import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/features/auth/presentation/auth_controller.dart';
import 'package:echo_app/shared/widgets/confirm_action_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionControllerProvider).asData?.value;
    final authState = ref.watch(authControllerProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Echo'),
        actions: <Widget>[
          IconButton(
            tooltip: '退出登录',
            onPressed: authState.isBusy
                ? null
                : () async {
                    final confirmed = await showConfirmActionSheet(
                      context,
                      title: '要退出当前账号吗？',
                      actionLabel: '退出登录',
                    );
                    if (confirmed) {
                      await ref.read(authControllerProvider.notifier).logout();
                    }
                  },
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(Icons.graphic_eq_rounded, size: 72),
              const SizedBox(height: 20),
              Text('欢迎回来', style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 8),
              Text(
                '登录已完成，聊天与设备功能将在后续里程碑接入。',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              if (session?.availability.name ==
                  'temporarilyOffline') ...<Widget>[
                const SizedBox(height: 16),
                const Chip(label: Text('当前离线，登录凭证已保留')),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
