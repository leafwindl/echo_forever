import 'dart:async';

import 'package:echo_app/features/study_focus/data/study_focus_audio.dart';
import 'package:echo_app/features/study_focus/data/study_focus_providers.dart';
import 'package:echo_app/features/study_focus/domain/focus_session.dart';
import 'package:echo_app/features/study_focus/presentation/focus_video_view.dart';
import 'package:echo_app/features/study_focus/presentation/study_focus_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class StudyFocusPage extends ConsumerStatefulWidget {
  const StudyFocusPage({super.key});

  @override
  ConsumerState<StudyFocusPage> createState() => _StudyFocusPageState();
}

class _StudyFocusPageState extends ConsumerState<StudyFocusPage> {
  late final TextEditingController _goalController;
  late final FocusNode _goalFocusNode;
  late final StudyFocusAudio _audio;

  @override
  void initState() {
    super.initState();
    _goalController = TextEditingController();
    _goalFocusNode = FocusNode()..addListener(_handleGoalFocusChanged);
    _audio = ref.read(studyFocusAudioProvider);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_audio.play());
    });
  }

  @override
  void dispose() {
    unawaited(_audio.stop());
    _goalFocusNode
      ..removeListener(_handleGoalFocusChanged)
      ..dispose();
    _goalController.dispose();
    super.dispose();
  }

  void _handleGoalFocusChanged() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final value = ref.watch(studyFocusControllerProvider);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        systemNavigationBarColor: Colors.black,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
      child: Scaffold(
        backgroundColor: Colors.black,
        body: value.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => _ErrorBody(
            message: '学习页面暂时无法打开',
            onRetry: () => ref.invalidate(studyFocusControllerProvider),
          ),
          data: (state) => PopScope(
            canPop: state.session == null,
            child: _buildBody(context, state),
          ),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context, StudyFocusState state) {
    final videoPlaying = state.session == null && state.result == null
        ? true
        : state.isRunning;
    final overlay = state.result != null && state.session == null
        ? _ResultView(
            session: state.result!,
            onAgain: () =>
                ref.read(studyFocusControllerProvider.notifier).dismissResult(),
            onExit: () => context.pop(),
          )
        : state.session != null
        ? _RunningView(
            state: state,
            onPause: () =>
                ref.read(studyFocusControllerProvider.notifier).pause(),
            onResume: () =>
                ref.read(studyFocusControllerProvider.notifier).resume(),
            onFinish: _finishEarly,
          )
        : _SetupView(
            state: state,
            goalController: _goalController,
            goalFocusNode: _goalFocusNode,
            onDurationChanged: (seconds) => ref
                .read(studyFocusControllerProvider.notifier)
                .setDuration(seconds),
            onCustomDuration: _pickCustomDuration,
            onActivityChanged: (type) => ref
                .read(studyFocusControllerProvider.notifier)
                .setActivityType(type),
            onStart: _start,
          );

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        FocusVideoView(
          key: const ValueKey<String>('study-focus-video'),
          playing: videoPlaying,
        ),
        const ColoredBox(color: Color(0x33000000)),
        SafeArea(
          bottom: false,
          child: Column(
            children: <Widget>[
              if (state.session == null && state.result == null)
                _TopBar(onBack: () => context.pop(), onHistory: _showHistory),
              Expanded(child: overlay),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _start() async {
    await ref
        .read(studyFocusControllerProvider.notifier)
        .start(shortGoal: _goalController.text);
    if (!mounted) return;
    final state = ref.read(studyFocusControllerProvider).asData?.value;
    if (state?.error != null) {
      _showMessage('学习计时暂时无法启动，请重试');
    }
  }

  Future<void> _finishEarly() async {
    await ref.read(studyFocusControllerProvider.notifier).finish();
  }

  Future<void> _pickCustomDuration() async {
    var rawMinutes = '30';
    String? errorText;
    final minutes = await showDialog<int>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('自定义时长'),
          content: TextFormField(
            initialValue: rawMinutes,
            autofocus: true,
            keyboardType: TextInputType.number,
            inputFormatters: <TextInputFormatter>[
              FilteringTextInputFormatter.digitsOnly,
            ],
            maxLength: 3,
            onChanged: (value) => rawMinutes = value,
            decoration: InputDecoration(
              labelText: '分钟',
              suffixText: '分钟',
              errorText: errorText,
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () {
                final value = int.tryParse(rawMinutes.trim());
                if (value == null || value < 1 || value > 180) {
                  setDialogState(() => errorText = '请输入 1～180 分钟');
                  return;
                }
                Navigator.of(dialogContext).pop(value);
              },
              child: const Text('确定'),
            ),
          ],
        ),
      ),
    );
    if (minutes != null && mounted) {
      ref.read(studyFocusControllerProvider.notifier).setDuration(minutes * 60);
    }
  }

  Future<void> _showHistory() async {
    final state = ref.read(studyFocusControllerProvider).asData?.value;
    if (state == null || !mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => _HistorySheet(sessions: state.history),
    );
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.onBack, required this.onHistory});

  final VoidCallback onBack;
  final VoidCallback onHistory;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
    child: Row(
      children: <Widget>[
        IconButton(
          tooltip: '返回',
          onPressed: onBack,
          color: Colors.white,
          icon: const Icon(Icons.keyboard_arrow_down_rounded),
        ),
        const Text(
          '一起学习',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        const Spacer(),
        IconButton(
          tooltip: '学习记录',
          onPressed: onHistory,
          color: Colors.white,
          icon: const Icon(Icons.history_rounded),
        ),
      ],
    ),
  );
}

class _SetupView extends StatelessWidget {
  const _SetupView({
    required this.state,
    required this.goalController,
    required this.goalFocusNode,
    required this.onDurationChanged,
    required this.onCustomDuration,
    required this.onActivityChanged,
    required this.onStart,
  });

  final StudyFocusState state;
  final TextEditingController goalController;
  final FocusNode goalFocusNode;
  final ValueChanged<int> onDurationChanged;
  final VoidCallback onCustomDuration;
  final ValueChanged<String> onActivityChanged;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    final durationKey = state.selectedDurationSeconds == 25 * 60
        ? 25 * 60
        : state.selectedDurationSeconds == 50 * 60
        ? 50 * 60
        : -1;
    return Align(
      alignment: Alignment.bottomCenter,
      child: ColoredBox(
        color: const Color(0xB8000000),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const Text(
                '专注时长',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: <Widget>[
                  Expanded(
                    child: _DurationButton(
                      label: '25 分钟',
                      selected: durationKey == 25 * 60,
                      onPressed: () => onDurationChanged(25 * 60),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _DurationButton(
                      label: '50 分钟',
                      selected: durationKey == 50 * 60,
                      onPressed: () => onDurationChanged(50 * 60),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _DurationButton(
                      label: '自定义',
                      selected: durationKey == -1,
                      onPressed: onCustomDuration,
                    ),
                  ),
                ],
              ),
              if (durationKey == -1) ...<Widget>[
                const SizedBox(height: 8),
                Text(
                  '当前自定义：${state.selectedDurationSeconds ~/ 60} 分钟',
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.78)),
                ),
              ],
              const SizedBox(height: 18),
              const Text(
                '学习内容',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: studyActivityTypes
                    .map(
                      (type) => ChoiceChip(
                        label: Text(type),
                        selected: state.selectedActivityType == type,
                        onSelected: (_) => onActivityChanged(type),
                      ),
                    )
                    .toList(growable: false),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: goalController,
                focusNode: goalFocusNode,
                maxLength: 80,
                maxLines: 1,
                style: const TextStyle(color: Color(0xFF202124)),
                textInputAction: TextInputAction.done,
                decoration: InputDecoration(
                  hintText: goalFocusNode.hasFocus ? null : '短目标（可选）',
                  hintStyle: const TextStyle(color: Color(0xFF80868B)),
                  counterText: '',
                  isDense: true,
                  filled: true,
                  fillColor: const Color(0xEFFFFFFF),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  prefixIcon: const Icon(
                    Icons.flag_outlined,
                    color: Color(0xFF5F6368),
                    size: 20,
                  ),
                  enabledBorder: const OutlineInputBorder(
                    borderSide: BorderSide(color: Colors.transparent),
                  ),
                  focusedBorder: const OutlineInputBorder(
                    borderSide: BorderSide(color: Color(0xFF6E61AF)),
                  ),
                ),
              ),
              const SizedBox(height: 4),
              FilledButton.icon(
                onPressed: state.isBusy ? null : onStart,
                icon: const Icon(Icons.play_arrow_rounded),
                label: Text(
                  '开始 ${_durationLabel(state.selectedDurationSeconds)}',
                ),
              ),
              const SizedBox(height: 12),
              _TodaySummary(seconds: state.todaySeconds),
            ],
          ),
        ),
      ),
    );
  }

  String _durationLabel(int seconds) => '${seconds ~/ 60} 分钟';
}

class _DurationButton extends StatelessWidget {
  const _DurationButton({
    required this.label,
    required this.selected,
    required this.onPressed,
  });

  final String label;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 42,
    child: OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        backgroundColor: selected
            ? const Color(0xFF6E61AF)
            : Colors.transparent,
        side: BorderSide(
          color: Colors.white.withValues(alpha: selected ? 0.8 : 0.45),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
      child: FittedBox(fit: BoxFit.scaleDown, child: Text(label, maxLines: 1)),
    ),
  );
}

class _RunningView extends StatelessWidget {
  const _RunningView({
    required this.state,
    required this.onPause,
    required this.onResume,
    required this.onFinish,
  });

  final StudyFocusState state;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onFinish;

  @override
  Widget build(BuildContext context) {
    final session = state.session!;
    final progress = session.plannedDurationSeconds == 0
        ? 0.0
        : (state.elapsedSeconds / session.plannedDurationSeconds).clamp(
            0.0,
            1.0,
          );
    final paused = state.isPaused;
    return Align(
      alignment: Alignment.bottomCenter,
      child: ColoredBox(
        color: const Color(0x99000000),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 30),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                session.shortGoal.isEmpty
                    ? session.activityType
                    : '${session.activityType} · ${session.shortGoal}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.88),
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                _formatDuration(state.remainingSeconds),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 58,
                  fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: LinearProgressIndicator(
                  minHeight: 6,
                  value: progress,
                  backgroundColor: Colors.white.withValues(alpha: 0.25),
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  FilledButton.icon(
                    onPressed: state.isBusy
                        ? null
                        : (paused ? onResume : onPause),
                    icon: Icon(paused ? Icons.play_arrow : Icons.pause),
                    label: Text(paused ? '继续' : '暂停'),
                  ),
                  const SizedBox(width: 12),
                  OutlinedButton.icon(
                    onPressed: state.isBusy ? null : onFinish,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: BorderSide(
                        color: Colors.white.withValues(alpha: 0.7),
                      ),
                    ),
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: const Text('结束本轮'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatDuration(int seconds) {
    final minutes = seconds ~/ 60;
    final remaining = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remaining.toString().padLeft(2, '0')}';
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView({
    required this.session,
    required this.onAgain,
    required this.onExit,
  });

  final FocusSession session;
  final VoidCallback onAgain;
  final VoidCallback onExit;

  @override
  Widget build(BuildContext context) {
    final completed = session.status == FocusSessionStatus.completed;
    return Align(
      alignment: Alignment.center,
      child: ColoredBox(
        color: const Color(0x99000000),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 26, 20, 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                completed
                    ? Icons.check_circle_outline
                    : Icons.pause_circle_outline,
                size: 54,
                color: Colors.white,
              ),
              const SizedBox(height: 12),
              Text(
                completed ? '这一轮完成了' : '这一轮提前结束',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '实际学习 ${_formatMinutes(session.elapsedSeconds)} · ${session.activityType}',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white.withValues(alpha: 0.82)),
              ),
              if (session.shortGoal.isNotEmpty) ...<Widget>[
                const SizedBox(height: 6),
                Text(
                  session.shortGoal,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.82)),
                ),
              ],
              const SizedBox(height: 22),
              FilledButton.icon(
                onPressed: onAgain,
                icon: const Icon(Icons.replay_rounded),
                label: const Text('再来一轮'),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: onExit,
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: BorderSide(color: Colors.white.withValues(alpha: 0.7)),
                ),
                icon: const Icon(Icons.check_rounded),
                label: const Text('结束学习'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatMinutes(int seconds) {
    final minutes = seconds ~/ 60;
    final remainder = seconds % 60;
    if (remainder == 0) return '$minutes 分钟';
    return '$minutes 分 ${remainder.toString().padLeft(2, '0')} 秒';
  }
}

class _TodaySummary extends StatelessWidget {
  const _TodaySummary({required this.seconds});

  final int seconds;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Text(
      '今天已学习 ${seconds ~/ 60} 分钟',
      style: TextStyle(color: Colors.white.withValues(alpha: 0.75)),
    ),
  );
}

class _HistorySheet extends StatelessWidget {
  const _HistorySheet({required this.sessions});

  final List<FocusSession> sessions;

  @override
  Widget build(BuildContext context) {
    if (sessions.isEmpty) {
      return const SafeArea(
        child: Padding(
          padding: EdgeInsets.fromLTRB(24, 12, 24, 36),
          child: Text('还没有学习记录，先开始一轮吧。'),
        ),
      );
    }
    return SafeArea(
      child: ListView.separated(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        itemCount: sessions.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final session = sessions[index];
          final date = session.endedAt?.toLocal();
          return ListTile(
            leading: Icon(
              session.status == FocusSessionStatus.completed
                  ? Icons.check_circle_outline
                  : Icons.stop_circle_outlined,
            ),
            title: Text(
              session.shortGoal.isEmpty
                  ? session.activityType
                  : '${session.activityType} · ${session.shortGoal}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(
              '${session.elapsedSeconds ~/ 60} 分钟${date == null ? '' : ' · ${date.month}/${date.day}'}',
            ),
          );
        },
      ),
    );
  }
}

class _ErrorBody extends StatelessWidget {
  const _ErrorBody({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: Colors.black,
    child: Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.cloud_off_rounded, size: 48, color: Colors.white),
            const SizedBox(height: 14),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('重试'),
            ),
          ],
        ),
      ),
    ),
  );
}
