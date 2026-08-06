import 'package:echo_app/features/app_update/presentation/app_update_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AppUpdateOverlay extends ConsumerWidget {
  const AppUpdateOverlay({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appUpdateControllerProvider);
    final release = state.release;
    if (!state.showsUpdatePanel || release == null) {
      return child;
    }
    final mandatory = release.mandatory;
    return PopScope(
      canPop: !mandatory,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          child,
          const ModalBarrier(dismissible: false, color: Colors.black54),
          SafeArea(
            child: Align(
              alignment: Alignment.center,
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: AlertDialog(
                  title: Text(mandatory ? '需要更新 Echo' : 'Echo 有新版本'),
                  content: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 420),
                    child: _UpdateContent(state: state),
                  ),
                  actions: _actions(context, ref, state),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _actions(
    BuildContext context,
    WidgetRef ref,
    AppUpdateState state,
  ) {
    final controller = ref.read(appUpdateControllerProvider.notifier);
    final widgets = <Widget>[];
    if (state.release?.mandatory != true && !state.isBusy) {
      widgets.add(
        TextButton(onPressed: controller.dismiss, child: const Text('稍后')),
      );
    }
    final action = switch (state.phase) {
      AppUpdatePhase.available => ('立即更新', Icons.system_update_alt_rounded),
      AppUpdatePhase.permissionRequired => ('打开安装权限', Icons.settings_outlined),
      AppUpdatePhase.readyToInstall || AppUpdatePhase.launchingInstaller => (
        '打开安装程序',
        Icons.install_mobile_rounded,
      ),
      AppUpdatePhase.failed => ('重试', Icons.refresh_rounded),
      _ => null,
    };
    if (action != null) {
      widgets.add(
        FilledButton.icon(
          onPressed: () {
            if (state.phase == AppUpdatePhase.readyToInstall ||
                state.phase == AppUpdatePhase.launchingInstaller) {
              controller.launchInstaller();
            } else {
              controller.startUpdate();
            }
          },
          icon: Icon(action.$2),
          label: Text(action.$1),
        ),
      );
    }
    return widgets;
  }
}

class _UpdateContent extends StatelessWidget {
  const _UpdateContent({required this.state});

  final AppUpdateState state;

  @override
  Widget build(BuildContext context) {
    final release = state.release!;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            '版本 ${release.versionName}  ·  ${_formatBytes(release.sizeBytes)}',
          ),
          if (release.releaseNotes.isNotEmpty) ...<Widget>[
            const SizedBox(height: 12),
            ...release.releaseNotes.map(
              (note) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text('• $note'),
              ),
            ),
          ],
          const SizedBox(height: 12),
          if (state.phase == AppUpdatePhase.permissionRequired)
            const Text('请允许 Echo 安装未知应用，返回后再次点击继续更新。'),
          if (state.phase == AppUpdatePhase.downloading) ...<Widget>[
            LinearProgressIndicator(value: state.progress),
            const SizedBox(height: 8),
            Text(
              state.progress == null
                  ? '正在下载安装包…'
                  : '正在下载 ${(state.progress! * 100).round()}%',
            ),
          ],
          if (state.phase == AppUpdatePhase.verifying) ...<Widget>[
            const LinearProgressIndicator(),
            const SizedBox(height: 8),
            const Text('正在校验安装包和签名…'),
          ],
          if (state.phase == AppUpdatePhase.readyToInstall)
            const Text('安装包已校验，准备打开系统安装程序。'),
          if (state.phase == AppUpdatePhase.launchingInstaller)
            const Text('请在系统安装程序中确认更新；取消后可再次打开。'),
          if (state.phase == AppUpdatePhase.failed)
            Text(
              state.errorMessage ?? '更新失败，请重试',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
        ],
      ),
    );
  }
}

String _formatBytes(int bytes) {
  final megabytes = bytes / (1024 * 1024);
  return '${megabytes.toStringAsFixed(megabytes >= 10 ? 0 : 1)} MB';
}
