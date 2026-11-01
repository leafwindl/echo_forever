import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/chat/presentation/chat_controller.dart';
import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class PersonaPage extends ConsumerWidget {
  const PersonaPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final relationship = ref.watch(relationshipStateProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('关于她'),
        leading: BackButton(onPressed: () => context.pop()),
        actions: <Widget>[
          IconButton(
            tooltip: '长期记忆',
            onPressed: () => context.pushNamed(RouteNames.memory),
            icon: const Icon(Icons.bookmark_outline_rounded),
          ),
          IconButton(
            tooltip: '刷新',
            onPressed: () => ref.invalidate(relationshipStateProvider),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      const Icon(Icons.favorite_rounded, size: 44),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              'Echo · AI 陪伴伙伴',
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '关系由相处慢慢形成，不用在这里调整人格。',
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  relationship.when(
                    loading: () => const EchoLoadingView(label: '正在加载关系'),
                    error: (error, _) => _RelationshipError(
                      onRetry: () => ref.invalidate(relationshipStateProvider),
                    ),
                    data: (state) => _RelationshipCard(
                      state: state,
                      onOpenProposal: state.pendingProposal == null
                          ? null
                          : () => _showProposalDialog(context, ref, state),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Text(
                    '聊天、长期记忆、关系、提醒和称呼边界会在这里一起重置；账号、设备和你的称呼保留。',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: () => _confirmReset(context, ref),
                    icon: const Icon(Icons.link_off_rounded),
                    label: const Text('重置关系'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _confirmReset(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('重置关系'),
        content: const Text(
          '聊天、长期记忆、关系、提醒和称呼边界都会清空，关系回到初识；'
          '账号、设备和你的称呼保留。这个操作不能撤销。',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('确认重置'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    try {
      await ref.read(personaRepositoryProvider).resetCompanionship();
      ref.invalidate(relationshipStateProvider);
      ref.invalidate(chatControllerProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('已重新开始，账号和设备保留')),
        );
      }
    } on Object catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('重置失败：$error')),
        );
      }
    }
  }

  Future<void> _showProposalDialog(
    BuildContext context,
    WidgetRef ref,
    RelationshipStateDto state,
  ) async {
    final proposal = state.pendingProposal;
    if (proposal == null) return;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('和 Echo 的关系'),
        content: Text(
          'Echo 想和你确认：从现在开始，做${proposal.directionLabel}吗？',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('再想想'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('愿意'),
          ),
        ],
      ),
    );
    try {
      if (accepted == true) {
        await ref
            .read(personaRepositoryProvider)
            .acceptRelationshipProposal(proposal.proposalId);
      } else {
        await ref
            .read(personaRepositoryProvider)
            .deferRelationshipProposal(proposal.proposalId);
      }
      ref.invalidate(relationshipStateProvider);
    } on Object catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('关系确认失败：$error')),
        );
      }
    }
  }
}

class _RelationshipCard extends StatelessWidget {
  const _RelationshipCard({
    required this.state,
    required this.onOpenProposal,
  });

  final RelationshipStateDto state;
  final VoidCallback? onOpenProposal;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('关系', style: Theme.of(context).textTheme.labelMedium),
            Text(
              state.relationshipTypeLabel,
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 12),
            Row(
              children: <Widget>[
                Expanded(
                  child: _Metric(
                    label: '互动',
                    value: '${state.interactionTurns} 次',
                  ),
                ),
                Expanded(
                  child: _Metric(
                    label: '活跃',
                    value: '${state.activeDays} 天',
                  ),
                ),
              ],
            ),
            if (onOpenProposal != null) ...<Widget>[
              const SizedBox(height: 14),
              FilledButton(
                onPressed: onOpenProposal,
                child: Text(
                  '查看确认窗口（${state.pendingProposal!.directionLabel}）',
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(label, style: Theme.of(context).textTheme.labelSmall),
        Text(value, style: Theme.of(context).textTheme.titleMedium),
      ],
    );
  }
}

class _RelationshipError extends StatelessWidget {
  const _RelationshipError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          child: Text(
            '关系加载失败',
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ),
        TextButton(onPressed: onRetry, child: const Text('重试')),
      ],
    );
  }
}
