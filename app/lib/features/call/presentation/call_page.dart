import 'dart:async';

import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:echo_app/features/call/presentation/call_controller.dart';
import 'package:echo_app/shared/widgets/character_renderer.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class CallPage extends ConsumerStatefulWidget {
  const CallPage({super.key});

  @override
  ConsumerState<CallPage> createState() => _CallPageState();
}

class _CallPageState extends ConsumerState<CallPage> {
  Timer? _elapsedTimer;
  final DateTime _startedAt = DateTime.now();
  Duration _elapsed = Duration.zero;

  @override
  void initState() {
    super.initState();
    _elapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() => _elapsed = DateTime.now().difference(_startedAt));
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(ref.read(callControllerProvider.notifier).connect());
      }
    });
  }

  @override
  void dispose() {
    _elapsedTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(callControllerProvider);
    ref.listen(callControllerProvider.select((value) => value.phase), (
      previous,
      next,
    ) {
      if (next == CallPhase.ended && mounted && context.canPop()) context.pop();
    });
    return Scaffold(
      appBar: AppBar(
        title: const Text('与 Echo 通话'),
        automaticallyImplyLeading: false,
        actions: <Widget>[
          IconButton(
            key: const Key('call-hangup-top'),
            tooltip: '结束通话',
            onPressed: state.phase == CallPhase.ended ? null : _hangUp,
            icon: const Icon(Icons.call_end_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _formatDuration(_elapsed),
                key: const Key('call-elapsed'),
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
            Expanded(
              flex: 5,
              child: StaticCharacterRenderer(
                state: _characterDisplayState(state.phase),
                key: const Key('call-character'),
              ),
            ),
            Expanded(
              flex: 4,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 4, 24, 12),
                child: Column(
                  children: <Widget>[
                    Text(
                      _statusLabel(state.phase),
                      key: const Key('call-status'),
                      style: Theme.of(context).textTheme.titleMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: SingleChildScrollView(
                        key: const Key('call-captions'),
                        child: Column(
                          children: <Widget>[
                            if ((state.partialText.isNotEmpty ||
                                state.userText.isNotEmpty))
                              _Caption(
                                speaker: '你',
                                text: state.userText.isNotEmpty
                                    ? state.userText
                                    : state.partialText,
                              ),
                            if (state.echoCaption.isNotEmpty)
                              _Caption(
                                speaker: 'Echo',
                                text: state.echoCaption,
                              ),
                            if (state.usingFallback)
                              const Padding(
                                padding: EdgeInsets.only(top: 6),
                                child: Text(
                                  '正在使用整段语音识别',
                                  key: Key('call-fallback-label'),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                    if (state.errorMessage != null)
                      MaterialBanner(
                        key: const Key('call-error'),
                        content: Text(state.errorMessage!),
                        actions: <Widget>[
                          TextButton(
                            onPressed: () => ref
                                .read(callControllerProvider.notifier)
                                .clearError(),
                            child: const Text('知道了'),
                          ),
                        ],
                      ),
                    const SizedBox(height: 8),
                    _TalkButton(
                      state: state,
                      onStart: () => ref
                          .read(callControllerProvider.notifier)
                          .startRecording(),
                      onStop: () => ref
                          .read(callControllerProvider.notifier)
                          .stopRecording(),
                      onCancel: () => ref
                          .read(callControllerProvider.notifier)
                          .cancelRecording(),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
    );
  }

  Future<void> _hangUp() async {
    await ref.read(callControllerProvider.notifier).hangUp();
    if (mounted && context.canPop()) context.pop();
  }

  static String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.toString().padLeft(2, '0');
    final seconds = (duration.inSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  static String _statusLabel(CallPhase phase) => switch (phase) {
    CallPhase.connecting => '正在连接',
    CallPhase.ready || CallPhase.idle || CallPhase.userTurn => '按住下方按钮说话',
    CallPhase.recording => '正在听你说',
    CallPhase.recognizing => '正在听清内容',
    CallPhase.thinking => 'Echo 正在想',
    CallPhase.speaking => 'Echo 正在说话（按住可打断）',
    CallPhase.ended => '通话已结束',
    CallPhase.error => '连接失败',
  };
}

CharacterDisplayState _characterDisplayState(CallPhase phase) =>
    switch (phase) {
      CallPhase.recording => CharacterDisplayState.listening,
      CallPhase.recognizing ||
      CallPhase.thinking => CharacterDisplayState.thinking,
      CallPhase.speaking => CharacterDisplayState.speaking,
      _ => CharacterDisplayState.idle,
    };

class _TalkButton extends StatelessWidget {
  const _TalkButton({
    required this.state,
    required this.onStart,
    required this.onStop,
    required this.onCancel,
  });

  final CallState state;
  final Future<bool> Function() onStart;
  final Future<bool> Function() onStop;
  final Future<void> Function() onCancel;

  @override
  Widget build(BuildContext context) {
    final enabled = switch (state.phase) {
      CallPhase.idle ||
      CallPhase.ready ||
      CallPhase.userTurn ||
      CallPhase.recording ||
      CallPhase.speaking => true,
      _ => false,
    };
    final scale = 1 + state.amplitude * .18;
    return Semantics(
      button: true,
      label: state.isRecording ? '松开发送，向上滑动取消' : '按住说话',
      child: GestureDetector(
        key: const Key('call-talk-button'),
        onLongPressStart: enabled ? (_) => unawaited(onStart()) : null,
        onLongPressEnd: enabled
            ? (_) => state.isRecording ? unawaited(onStop()) : null
            : null,
        onLongPressCancel: enabled ? () => unawaited(onCancel()) : null,
        child: AnimatedScale(
          scale: state.isRecording ? scale : 1,
          duration: const Duration(milliseconds: 80),
          child: Container(
            width: 116,
            height: 64,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: enabled
                  ? state.isRecording
                        ? Theme.of(context).colorScheme.errorContainer
                        : Theme.of(context).colorScheme.primaryContainer
                  : Theme.of(context).colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(32),
            ),
            child: Text(state.isRecording ? '松开发送' : '按住说话'),
          ),
        ),
      ),
    );
  }
}

class _Caption extends StatelessWidget {
  const _Caption({required this.speaker, required this.text});

  final String speaker;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Text(
        '$speaker：$text',
        style: Theme.of(context).textTheme.bodyLarge,
        textAlign: TextAlign.center,
      ),
    );
  }
}
