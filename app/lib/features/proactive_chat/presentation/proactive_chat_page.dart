import 'package:echo_app/features/proactive_chat/domain/proactive_chat.dart';
import 'package:echo_app/features/proactive_chat/presentation/proactive_chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
        title: const Text('主动聊天与提醒'),
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
          const SizedBox(height: 12),
          Text('频率', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          SegmentedButton<ProactivityLevel>(
            segments: ProactivityLevel.values
                .map(
                  (level) => ButtonSegment<ProactivityLevel>(
                    value: level,
                    label: Text(level.label),
                  ),
                )
                .toList(growable: false),
            selected: <ProactivityLevel>{preferences.proactivityLevel},
            onSelectionChanged: !preferences.enabled || state.isSaving
                ? null
                : (levels) => controller.savePreferences(
                    preferences.copyWith(proactivityLevel: levels.first),
                  ),
          ),
          const SizedBox(height: 8),
          Text(
            _frequencyDescription(preferences.proactivityLevel),
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
          Text('已安排的任务', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          if (state.schedules.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text('还没有任务。你可以在聊天里直接说“晚上八点提醒我喝水”。'),
            ),
          for (final schedule in state.schedules)
            _ScheduleTile(
              schedule: schedule,
              busy: state.isSaving,
              onToggle: () => controller.setScheduleStatus(
                schedule,
                schedule.isActive ? 'paused' : 'active',
              ),
              onDelete: () => controller.deleteSchedule(schedule),
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

  String _frequencyDescription(ProactivityLevel level) => switch (level) {
    ProactivityLevel.conservative => '至少 24 小时未互动，每周最多 4 次，最小间隔 24 小时。',
    ProactivityLevel.balanced => '至少 6 小时未互动，每天最多 4 次，最小间隔 6 小时。',
    ProactivityLevel.active => '至少 2 小时未互动，每天最多 6 次，最小间隔 2 小时。',
  };
}

class _ScheduleTile extends StatelessWidget {
  const _ScheduleTile({
    required this.schedule,
    required this.busy,
    required this.onToggle,
    required this.onDelete,
  });

  final ChatSchedule schedule;
  final bool busy;
  final VoidCallback onToggle;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final next = schedule.nextRunAt;
    final date = next == null
        ? '时间待定'
        : '${next.year}-${next.month.toString().padLeft(2, '0')}-${next.day.toString().padLeft(2, '0')} '
              '${next.hour.toString().padLeft(2, '0')}:${next.minute.toString().padLeft(2, '0')}';
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(
        schedule.displayLabel,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        '$date  ·  ${schedule.isActive ? '进行中' : schedule.status}',
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          IconButton(
            tooltip: schedule.isActive ? '暂停' : '恢复',
            onPressed: busy || schedule.status == 'cancelled' ? null : onToggle,
            icon: Icon(
              schedule.isActive
                  ? Icons.pause_rounded
                  : Icons.play_arrow_rounded,
            ),
          ),
          IconButton(
            tooltip: '删除',
            onPressed: busy ? null : onDelete,
            icon: const Icon(Icons.delete_outline_rounded),
          ),
        ],
      ),
    );
  }
}
