import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:echo_app/features/persona/presentation/persona_editor_fields.dart';
import 'package:echo_app/features/persona/presentation/persona_form_model.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:echo_app/shared/widgets/primary_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class PersonaPage extends ConsumerStatefulWidget {
  const PersonaPage({super.key});

  @override
  ConsumerState<PersonaPage> createState() => _PersonaPageState();
}

class _PersonaPageState extends ConsumerState<PersonaPage> {
  PersonaDraft _draft = PersonaDraft.defaults();
  var _dirty = false;

  @override
  Widget build(BuildContext context) {
    final personaState = ref.watch(personaControllerProvider);
    final current = personaState.asData?.value;
    final relationshipState = ref.watch(relationshipStateProvider);
    ref.listen(personaControllerProvider, (previous, next) {
      final nextPersona = next.asData?.value;
      if (nextPersona == null || _dirty) {
        return;
      }
      final nextDraft = PersonaDraft.fromPersona(nextPersona.persona);
      if (_draft != nextDraft) {
        setState(() {
          _draft = nextDraft;
        });
      }
    });

    if (current == null && personaState.isLoading) {
      return const Scaffold(
        body: SafeArea(child: EchoLoadingView(label: '正在加载个性化设置')),
      );
    }

    final errorText = current?.error?.detail;

    return Scaffold(
      appBar: AppBar(
        title: const Text('个性化设置'),
        leading: BackButton(onPressed: () => context.pop()),
        actions: <Widget>[
          IconButton(
            tooltip: '长期记忆',
            onPressed: personaState.isLoading
                ? null
                : () => context.pushNamed(RouteNames.memory),
            icon: const Icon(Icons.bookmark_outline_rounded),
          ),
          IconButton(
            tooltip: '重新加载',
            onPressed: personaState.isLoading
                ? null
                : () => ref.read(personaControllerProvider.notifier).refresh(),
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
                      const Icon(Icons.tune_rounded, size: 44),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              '个性化设置',
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '这里的设置会直接影响文字聊天和硬件语音中的称呼、语气、关系节奏和长期记忆。',
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  _RelationshipSummary(
                    relationshipState: relationshipState,
                    onRetry: () => ref.invalidate(relationshipStateProvider),
                  ),
                  if (errorText != null) ...<Widget>[
                    const SizedBox(height: 16),
                    Material(
                      color: Theme.of(context).colorScheme.errorContainer,
                      borderRadius: BorderRadius.circular(12),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: <Widget>[
                            Expanded(
                              child: Text(
                                errorText,
                                style: TextStyle(
                                  color: Theme.of(
                                    context,
                                  ).colorScheme.onErrorContainer,
                                ),
                              ),
                            ),
                            TextButton(
                              onPressed: personaState.isLoading
                                  ? null
                                  : () => ref
                                        .read(
                                          personaControllerProvider.notifier,
                                        )
                                        .refresh(),
                              child: const Text('重试'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 24),
                  PersonaEditorFields(
                    draft: _draft,
                    onChanged: (next) {
                      setState(() {
                        _draft = next;
                        _dirty = true;
                      });
                    },
                  ),
                  const SizedBox(height: 8),
                  PrimaryButton(
                    label: '保存设置',
                    isLoading: current?.isSaving ?? false,
                    onPressed: personaState.isLoading ? null : _save,
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: current?.isSaving == true
                              ? null
                              : _resetPersona,
                          icon: const Icon(Icons.restart_alt_rounded),
                          label: const Text('恢复默认'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: current?.isSaving == true
                              ? null
                              : _resetRelationship,
                          icon: const Icon(Icons.link_off_rounded),
                          label: const Text('重置关系'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _save() async {
    final persona = await ref
        .read(personaControllerProvider.notifier)
        .updatePersona(_draft.toUpdate());
    if (!mounted) {
      return;
    }
    if (persona == null) {
      final detail = ref
          .read(personaControllerProvider)
          .asData
          ?.value
          .error
          ?.detail;
      if (detail != null) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(detail)));
      }
      return;
    }
    setState(() {
      _draft = PersonaDraft.fromPersona(persona);
      _dirty = false;
    });
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('设置已保存')));
  }

  Future<void> _resetPersona() async {
    final confirmed = await _confirmDanger(
      title: '恢复默认设置',
      content: '只会重置个性化偏好，不会删除长期记忆或聊天记录。',
      actionLabel: '恢复默认',
    );
    if (!confirmed || !mounted) {
      return;
    }
    final persona = await ref
        .read(personaControllerProvider.notifier)
        .resetPersona();
    if (!mounted || persona == null) {
      return;
    }
    setState(() {
      _draft = PersonaDraft.fromPersona(persona);
      _dirty = false;
    });
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('已恢复默认设置')));
  }

  Future<void> _resetRelationship() async {
    final confirmed = await _confirmDanger(
      title: '重置关系进度',
      content: 'Echo 会把关系状态重新回到初识阶段，个性化设置和长期记忆不会被删除。',
      actionLabel: '重置关系',
    );
    if (!confirmed || !mounted) {
      return;
    }
    final relationship = await ref
        .read(personaControllerProvider.notifier)
        .resetRelationship();
    if (!mounted || relationship == null) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('关系进度已重置')));
  }

  Future<bool> _confirmDanger({
    required String title,
    required String content,
    required String actionLabel,
  }) async {
    return await showDialog<bool>(
          context: context,
          builder: (context) {
            return AlertDialog(
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
            );
          },
        ) ??
        false;
  }
}

class _RelationshipSummary extends StatelessWidget {
  const _RelationshipSummary({
    required this.relationshipState,
    required this.onRetry,
  });

  final AsyncValue<RelationshipStateDto> relationshipState;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return relationshipState.when(
      data: (relationship) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text('关系进度', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  _InfoChip(label: '阶段', value: relationship.stageLabel),
                  _InfoChip(
                    label: '互动',
                    value: '${relationship.interactionTurns} 次',
                  ),
                  _InfoChip(label: '活跃', value: '${relationship.activeDays} 天'),
                  _InfoChip(
                    label: '亲近',
                    value: relationship.affectionPermission,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
      loading: () => const LinearProgressIndicator(minHeight: 2),
      error: (_, _) => Row(
        children: <Widget>[
          Expanded(
            child: Text(
              '关系进度加载失败',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
          TextButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Text('$label · $value'),
      ),
    );
  }
}
