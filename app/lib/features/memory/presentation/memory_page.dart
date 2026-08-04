import 'package:echo_app/features/memory/domain/memory.dart';
import 'package:echo_app/features/memory/presentation/memory_controller.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class MemoryPage extends ConsumerWidget {
  const MemoryPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncState = ref.watch(memoryControllerProvider);
    final state = asyncState.asData?.value;
    if (state == null && asyncState.isLoading) {
      return const Scaffold(
        body: SafeArea(child: EchoLoadingView(label: '正在加载长期记忆')),
      );
    }

    final current = state ?? const MemoryState.loading();

    return Scaffold(
      appBar: AppBar(
        title: Text('长期记忆 (${current.count})'),
        actions: <Widget>[
          IconButton(
            tooltip: '刷新',
            onPressed: current.isLoading
                ? null
                : () => ref.read(memoryControllerProvider.notifier).refresh(),
            icon: const Icon(Icons.refresh_rounded),
          ),
          IconButton(
            tooltip: '清空',
            onPressed: current.canClear
                ? () => _clearMemories(context, ref)
                : null,
            icon: const Icon(Icons.delete_sweep_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: SegmentedButton<MemoryTab>(
                      segments: <ButtonSegment<MemoryTab>>[
                        ButtonSegment<MemoryTab>(
                          value: MemoryTab.active,
                          label: Text(MemoryTab.active.label),
                          icon: Icon(MemoryTab.active.icon),
                        ),
                        ButtonSegment<MemoryTab>(
                          value: MemoryTab.deleted,
                          label: Text(MemoryTab.deleted.label),
                          icon: Icon(MemoryTab.deleted.icon),
                        ),
                      ],
                      selected: <MemoryTab>{current.tab},
                      onSelectionChanged: (selection) => ref
                          .read(memoryControllerProvider.notifier)
                          .switchTab(selection.first),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    '${current.memories.length}/${current.count}',
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                ],
              ),
            ),
            if (current.isLoading) const LinearProgressIndicator(minHeight: 2),
            if (current.error != null)
              Material(
                color: Theme.of(context).colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 10,
                  ),
                  child: Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          current.error!.detail ?? '长期记忆加载失败',
                          style: TextStyle(
                            color: Theme.of(
                              context,
                            ).colorScheme.onErrorContainer,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: () => ref
                            .read(memoryControllerProvider.notifier)
                            .refresh(),
                        child: const Text('重试'),
                      ),
                    ],
                  ),
                ),
              ),
            Expanded(
              child:
                  current.isLoading &&
                      current.memories.isEmpty &&
                      current.error == null
                  ? const EchoLoadingView(label: '正在加载长期记忆')
                  : RefreshIndicator(
                      onRefresh: () async {
                        await ref
                            .read(memoryControllerProvider.notifier)
                            .refresh();
                      },
                      child: current.memories.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: <Widget>[
                                SizedBox(
                                  height:
                                      MediaQuery.sizeOf(context).height * 0.45,
                                  child: Center(
                                    child: _EmptyState(tab: current.tab),
                                  ),
                                ),
                              ],
                            )
                          : ListView.separated(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
                              itemCount: current.memories.length,
                              separatorBuilder: (context, index) =>
                                  const SizedBox(height: 12),
                              itemBuilder: (context, index) {
                                final memory = current.memories[index];
                                return _MemoryTile(
                                  memory: memory,
                                  deleting:
                                      current.deletingId == memory.memoryId,
                                  showDelete: current.tab == MemoryTab.active,
                                  onDelete: () =>
                                      _deleteMemory(context, ref, memory),
                                );
                              },
                            ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _deleteMemory(
    BuildContext context,
    WidgetRef ref,
    MemoryRecord memory,
  ) async {
    final confirmed = await _confirm(
      context,
      title: '删除这条记忆',
      content: '删除后，Echo 不会继续使用这条长期记忆。',
      actionLabel: '删除',
    );
    if (!confirmed) {
      return;
    }
    await ref
        .read(memoryControllerProvider.notifier)
        .deleteMemory(memory.memoryId);
  }

  Future<void> _clearMemories(BuildContext context, WidgetRef ref) async {
    final confirmed = await _confirm(
      context,
      title: '清空长期记忆',
      content: '只会清空长期记忆，不会删除聊天记录。',
      actionLabel: '清空',
    );
    if (!confirmed) {
      return;
    }
    await ref.read(memoryControllerProvider.notifier).clearMemories();
  }

  Future<bool> _confirm(
    BuildContext context, {
    required String title,
    required String content,
    required String actionLabel,
  }) async {
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(title),
            content: Text(content),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: Text(actionLabel),
              ),
            ],
          ),
        ) ??
        false;
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.tab});

  final MemoryTab tab;

  @override
  Widget build(BuildContext context) {
    final isActive = tab == MemoryTab.active;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(
          isActive ? Icons.inbox_rounded : Icons.delete_outline_rounded,
          size: 44,
        ),
        const SizedBox(height: 12),
        Text(
          isActive ? '还没有长期记忆' : '没有已删除的记忆',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 6),
        Text(
          isActive ? '聊天中沉淀出的重要信息会出现在这里。' : '被软删除的记忆会暂时留在这里。',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ],
    );
  }
}

class _MemoryTile extends StatelessWidget {
  const _MemoryTile({
    required this.memory,
    required this.deleting,
    required this.showDelete,
    required this.onDelete,
  });

  final MemoryRecord memory;
  final bool deleting;
  final bool showDelete;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Expanded(
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: <Widget>[
                      _Pill(label: memory.memoryType.label),
                      _Pill(label: '重要度 ${memory.importance}'),
                      _Pill(
                        label: '置信 ${_formatConfidence(memory.confidence)}',
                      ),
                      _Pill(label: _formatUpdated(memory.updatedAt)),
                    ],
                  ),
                ),
                if (showDelete)
                  IconButton(
                    tooltip: '删除',
                    onPressed: deleting ? null : onDelete,
                    icon: deleting
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.delete_outline_rounded),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              memory.content,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 8),
            Row(
              children: <Widget>[
                _Pill(label: memory.status.label),
                if (memory.sourceMessageId != null) ...<Widget>[
                  const SizedBox(width: 8),
                  _Pill(label: '来源 #${memory.sourceMessageId}'),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  static String _formatConfidence(double value) {
    return '${(value * 100).round()}%';
  }

  static String _formatUpdated(String? value) {
    if (value == null || value.isEmpty) {
      return '更新时间未知';
    }
    final parsed = DateTime.tryParse(value);
    if (parsed == null) {
      return value;
    }
    final local = parsed.toLocal();
    final month = local.month.toString().padLeft(2, '0');
    final day = local.day.toString().padLeft(2, '0');
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return '$month-$day $hour:$minute';
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Text(label, style: Theme.of(context).textTheme.labelSmall),
      ),
    );
  }
}
