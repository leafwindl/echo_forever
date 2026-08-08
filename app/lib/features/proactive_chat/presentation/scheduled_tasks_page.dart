import 'package:echo_app/features/proactive_chat/domain/proactive_chat.dart';
import 'package:echo_app/features/proactive_chat/presentation/proactive_chat_controller.dart';
import 'package:echo_app/shared/widgets/confirm_action_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class ScheduledTasksPage extends ConsumerWidget {
  const ScheduledTasksPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(proactiveChatControllerProvider).asData?.value;
    if (state == null || state.isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final controller = ref.read(proactiveChatControllerProvider.notifier);
    return Scaffold(
      appBar: AppBar(
        title: const Text('定时任务'),
        actions: <Widget>[
          IconButton(
            tooltip: '刷新',
            onPressed: state.isSaving ? null : controller.refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: controller.refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
          children: <Widget>[
            if (state.schedules.isEmpty)
              const _EmptyTasks()
            else
              for (var index = 0; index < state.schedules.length; index++) ...[
                _ScheduleTile(
                  schedule: state.schedules[index],
                  busy: state.isSaving,
                  onToggle: () => controller.setScheduleStatus(
                    state.schedules[index],
                    state.schedules[index].isActive ? 'paused' : 'active',
                  ),
                  onDelete: () => _confirmDelete(
                    context,
                    controller,
                    state.schedules[index],
                  ),
                ),
                if (index < state.schedules.length - 1) const Divider(),
              ],
            if (state.error != null) ...<Widget>[
              const SizedBox(height: 16),
              Text(
                state.error!.detail ?? '任务暂时无法更新',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _confirmDelete(
    BuildContext context,
    ProactiveChatController controller,
    ChatSchedule schedule,
  ) async {
    final confirmed = await showConfirmActionSheet(
      context,
      title: '删除“${schedule.displayLabel}”？',
      message: '删除后 Echo 不会再执行这个任务。',
      actionLabel: '删除任务',
    );
    if (confirmed) await controller.deleteSchedule(schedule);
  }
}

class _EmptyTasks extends StatelessWidget {
  const _EmptyTasks();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 72),
      child: Column(
        children: <Widget>[
          Icon(
            Icons.event_available_rounded,
            size: 48,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 16),
          Text('还没有定时任务', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(
            '你可以在聊天里说“晚上八点提醒我喝水”。',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
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
    return ListTile(
      key: ValueKey<String>('scheduled-task-${schedule.scheduleId}'),
      contentPadding: EdgeInsets.zero,
      title: Text(
        schedule.displayLabel,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        '${_typeLabel(schedule.scheduleType)} · ${_formatDate(schedule.nextRunAt)} · '
        '${schedule.isActive ? '进行中' : '已暂停'}',
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          IconButton(
            tooltip: schedule.isActive ? '暂停' : '恢复',
            onPressed: busy ? null : onToggle,
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

  String _typeLabel(String value) => switch (value) {
    'daily' => '每天',
    'weekly' => '每周',
    _ => '一次性',
  };

  String _formatDate(DateTime? value) {
    if (value == null) return '时间待定';
    return '${value.year}-${value.month.toString().padLeft(2, '0')}-'
        '${value.day.toString().padLeft(2, '0')} '
        '${value.hour.toString().padLeft(2, '0')}:'
        '${value.minute.toString().padLeft(2, '0')}';
  }
}
