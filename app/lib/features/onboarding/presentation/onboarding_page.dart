import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/persona/presentation/persona_controller.dart';
import 'package:echo_app/features/persona/presentation/persona_editor_fields.dart';
import 'package:echo_app/features/persona/presentation/persona_form_model.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:echo_app/shared/widgets/primary_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class OnboardingPage extends ConsumerStatefulWidget {
  const OnboardingPage({super.key});

  @override
  ConsumerState<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends ConsumerState<OnboardingPage> {
  PersonaDraft _draft = PersonaDraft.defaults();
  var _dirty = false;

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(personaControllerProvider);
    final current = state.asData?.value;
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

    if (current == null && state.isLoading) {
      return const Scaffold(
        body: SafeArea(child: EchoLoadingView(label: '正在准备你的 Echo')),
      );
    }

    final errorText = current?.error?.detail;

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('首次设置'),
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
                  const Icon(Icons.auto_awesome_rounded, size: 44),
                  const SizedBox(height: 12),
                  Text(
                    '先认识你，再开始聊天',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '这一步会保存到服务端，也会在本地记住，之后可以再进个性化设置里调整。',
                    style: Theme.of(context).textTheme.bodyMedium,
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
                              onPressed: state.isLoading
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
                    label: '开始认识 Echo',
                    isLoading: current?.isSaving ?? false,
                    onPressed: state.isLoading ? null : _submit,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '以后仍然可以从个性化设置里修改。',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final preferredName = _draft.preferredName.trim();
    if (preferredName.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('先告诉 Echo 怎么称呼你')));
      return;
    }
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
    _dirty = false;
    context.goNamed(RouteNames.home);
  }
}
