import 'package:echo_app/features/presence/domain/presence.dart';
import 'package:echo_app/features/presence/presentation/presence_controller.dart';
import 'package:echo_app/shared/widgets/echo_error_view.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class PresencePage extends ConsumerWidget {
  const PresencePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(presenceProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('她的状态'),
        actions: <Widget>[
          IconButton(
            tooltip: '刷新',
            onPressed: () => ref.invalidate(presenceProvider),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: async.when(
          loading: () => const EchoLoadingView(label: '正在看她刚才在想什么'),
          error: (error, _) => EchoErrorView(
            message: '暂时看不到她的状态：$error',
            onRetry: () => ref.invalidate(presenceProvider),
          ),
          data: (snapshot) => RefreshIndicator(
            onRefresh: () async => ref.invalidate(presenceProvider),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
              children: <Widget>[
                _StatusCard(snapshot: snapshot),
                const SizedBox(height: 16),
                _BudgetCard(snapshot: snapshot),
                const SizedBox(height: 24),
                Row(
                  children: <Widget>[
                    Text(
                      '内心念头',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '${snapshot.thoughts.length} 条',
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  '她独处时产生的想法。默认只留在这里，不会自动发到聊天。',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                if (!snapshot.hasThoughts)
                  const _EmptyThoughts()
                else
                  ...snapshot.thoughts.map(
                    (thought) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _ThoughtCard(thought: thought),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.snapshot});

  final PresenceSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: snapshot.status == 'sleeping'
                      ? scheme.outline
                      : scheme.primary,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                snapshot.statusLabel,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              Icon(
                snapshot.enabled ? Icons.favorite_rounded : Icons.pause_circle,
                color: scheme.primary,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            snapshot.hasThoughts
                ? '她在安静的时候也会想一点事情。最近一次念头在下面。'
                : '她还在等一段安静的时间，暂时没有新的念头。',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          if (snapshot.lastThoughtAt != null) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              '最近念头：${_relativeTime(snapshot.lastThoughtAt!)}',
              style: Theme.of(context).textTheme.labelMedium,
            ),
          ],
        ],
      ),
    );
  }
}

class _BudgetCard extends StatelessWidget {
  const _BudgetCard({required this.snapshot});

  final PresenceSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final total = snapshot.dailyThoughtBudget <= 0
        ? 1
        : snapshot.dailyThoughtBudget;
    final used = snapshot.thoughtsUsed.clamp(0, total);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                '今天的念头',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const Spacer(),
              Text('$used / $total'),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: used / total,
              minHeight: 7,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '心跳每 15 分钟检查一次；只有值得的时候才会留下一个念头。',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _ThoughtCard extends StatelessWidget {
  const _ThoughtCard({required this.thought});

  final PresenceThought thought;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            thought.text,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.55),
          ),
          const SizedBox(height: 10),
          Row(
            children: <Widget>[
              Icon(
                Icons.nights_stay_outlined,
                size: 15,
                color: scheme.onSurfaceVariant,
              ),
              const SizedBox(width: 5),
              Text(
                thought.createdAt == null
                    ? '刚才'
                    : _relativeTime(thought.createdAt!),
                style: Theme.of(context).textTheme.labelSmall,
              ),
              const Spacer(),
              if (thought.salience >= 0.6)
                Text(
                  '记得比较深',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _EmptyThoughts extends StatelessWidget {
  const _EmptyThoughts();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 36),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Column(
        children: <Widget>[
          Icon(
            Icons.cloud_outlined,
            size: 36,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(height: 10),
          Text(
            '还没有独处念头',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          const SizedBox(height: 6),
          Text(
            '等她安静一会儿，这里会出现她刚才在想的事。',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

String _relativeTime(DateTime time) {
  final now = DateTime.now();
  final local = time.toLocal();
  final diff = now.difference(local);
  if (diff.inMinutes < 1) return '刚刚';
  if (diff.inMinutes < 60) return '${diff.inMinutes} 分钟前';
  if (diff.inHours < 24) return '${diff.inHours} 小时前';
  if (diff.inDays < 7) return '${diff.inDays} 天前';
  return '${local.month} 月 ${local.day} 日';
}
