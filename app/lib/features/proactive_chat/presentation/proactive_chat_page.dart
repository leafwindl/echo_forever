import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/proactive_chat/domain/proactive_chat.dart';
import 'package:echo_app/features/proactive_chat/presentation/proactive_chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class ProactiveChatPage extends ConsumerWidget {
  const ProactiveChatPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(proactiveChatControllerProvider).asData?.value;
    if (state == null || state.isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final controller = ref.read(proactiveChatControllerProvider.notifier);
    final preferences = state.preferences;
    return Scaffold(
      appBar: AppBar(
        title: const Text('主动聊天设置'),
        actions: <Widget>[
          IconButton(
            tooltip: '刷新',
            onPressed: state.isSaving ? null : controller.refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
        children: <Widget>[
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('主动聊天'),
            subtitle: const Text('允许 Echo 在合适的时机发起文字消息'),
            value: preferences.enabled,
            onChanged: state.isSaving
                ? null
                : (value) => controller.savePreferences(
                    preferences.copyWith(enabled: value),
                  ),
          ),
          const Divider(),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('允许 Echo 安排后续问候'),
            subtitle: const Text('例如在面试或重要行程之后再来问候一次'),
            value: preferences.allowEchoScheduling,
            onChanged: !preferences.enabled || state.isSaving
                ? null
                : (value) => controller.savePreferences(
                    preferences.copyWith(allowEchoScheduling: value),
                  ),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('允许自然主动聊天'),
            subtitle: const Text('在你一段时间未互动后，Echo 可以尝试自然开场'),
            value: preferences.allowSpontaneousChat,
            onChanged: !preferences.enabled || state.isSaving
                ? null
                : (value) => controller.savePreferences(
                    preferences.copyWith(allowSpontaneousChat: value),
                  ),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(
              preferences.paused
                  ? Icons.pause_circle_outline_rounded
                  : Icons.notifications_paused_outlined,
            ),
            title: Text(
              preferences.paused ? '已暂停主动联系' : '暂停主动联系',
            ),
            subtitle: Text(
              preferences.paused
                  ? (preferences.pauseIndefinite
                        ? '直到你主动恢复'
                        : '暂停到 ${preferences.pausedUntil ?? ''}')
                  : '也可以在聊天里说“这两天别主动找我”',
            ),
            trailing: preferences.paused
                ? TextButton(
                    onPressed: state.isSaving ? null : controller.resume,
                    child: const Text('恢复'),
                  )
                : TextButton(
                    onPressed: state.isSaving
                        ? null
                        : () => controller.pause(days: 2),
                    child: const Text('暂停两天'),
                  ),
          ),
          const SizedBox(height: 12),
          Text(
            'Echo 会在合适的时间自然联系，不需要反复调整频率。',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const Divider(height: 32),
          Text('通知与安静时段', style: Theme.of(context).textTheme.titleSmall),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('显示通知正文'),
            subtitle: const Text('默认隐藏，仅显示“Echo 发来了一条消息”'),
            value: preferences.notificationPreview,
            onChanged: state.isSaving
                ? null
                : (value) => controller.savePreferences(
                    preferences.copyWith(notificationPreview: value),
                  ),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('安静时段'),
            subtitle: Text(
              '${preferences.quietStart} - ${preferences.quietEnd}',
            ),
            trailing: const Icon(Icons.schedule_rounded),
            onTap: state.isSaving
                ? null
                : () => _editQuietHours(context, controller, preferences),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('用户明确提醒不顺延'),
            subtitle: const Text('关闭后，安静时段内的明确提醒会在安静时段结束后发送'),
            value: preferences.explicitReminderQuietPolicy == 'honor',
            onChanged: state.isSaving
                ? null
                : (value) => controller.savePreferences(
                    preferences.copyWith(
                      explicitReminderQuietPolicy: value ? 'honor' : 'defer',
                    ),
                  ),
          ),
          const Divider(height: 32),
          ListTile(
            key: const Key('open-scheduled-tasks'),
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.event_note_rounded),
            title: const Text('定时任务管理'),
            subtitle: Text(
              state.schedules.isEmpty
                  ? '查看 Echo 提醒和后续问候'
                  : '${state.schedules.length} 个进行中或暂停的任务',
            ),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => context.pushNamed(RouteNames.scheduledTasks),
          ),
          if (state.error != null) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              state.error!.detail ?? '设置暂时无法保存',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _editQuietHours(
    BuildContext context,
    ProactiveChatController controller,
    ProactiveChatPreferences preferences,
  ) async {
    final start = await showTimePicker(
      context: context,
      initialTime: _timeOfDay(preferences.quietStart),
      helpText: '安静时段开始',
    );
    if (start == null || !context.mounted) return;
    final end = await showTimePicker(
      context: context,
      initialTime: _timeOfDay(preferences.quietEnd),
      helpText: '安静时段结束',
    );
    if (end == null) return;
    await controller.savePreferences(
      preferences.copyWith(
        quietStart: _formatTime(start),
        quietEnd: _formatTime(end),
      ),
    );
  }

  TimeOfDay _timeOfDay(String value) {
    final fields = value.split(':');
    return TimeOfDay(
      hour: int.tryParse(fields.first) ?? 22,
      minute: fields.length > 1 ? int.tryParse(fields[1]) ?? 30 : 30,
    );
  }

  String _formatTime(TimeOfDay value) =>
      '${value.hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')}';

}
