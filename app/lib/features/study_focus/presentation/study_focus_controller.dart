import 'dart:async';

import 'package:echo_app/features/study_focus/data/study_focus_providers.dart';
import 'package:echo_app/features/study_focus/domain/focus_session.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

const studyActivityTypes = <String>['背单词', '刷题', '看课', '阅读', '其他'];

class StudyFocusState {
  const StudyFocusState({
    required this.session,
    required this.result,
    required this.history,
    required this.selectedDurationSeconds,
    required this.selectedActivityType,
    required this.now,
    required this.isBusy,
    this.error,
  });

  StudyFocusState.initial()
    : session = null,
      result = null,
      history = const <FocusSession>[],
      selectedDurationSeconds = 25 * 60,
      selectedActivityType = '背单词',
      now = DateTime.now().toUtc(),
      isBusy = false,
      error = null;

  final FocusSession? session;
  final FocusSession? result;
  final List<FocusSession> history;
  final int selectedDurationSeconds;
  final String selectedActivityType;
  final DateTime now;
  final bool isBusy;
  final Object? error;

  bool get isRunning => session?.status == FocusSessionStatus.running;
  bool get isPaused => session?.status == FocusSessionStatus.paused;
  bool get hasResult => result != null;
  int get todaySeconds {
    final today = DateTime.now();
    return history
        .where((item) {
          final date = item.endedAt?.toLocal();
          return date != null &&
              date.year == today.year &&
              date.month == today.month &&
              date.day == today.day;
        })
        .fold(0, (sum, item) => sum + item.elapsedSeconds);
  }

  int get remainingSeconds => session?.remainingAt(now) ?? 0;
  int get elapsedSeconds => session?.elapsedAt(now) ?? 0;

  StudyFocusState copyWith({
    FocusSession? session,
    bool clearSession = false,
    FocusSession? result,
    bool clearResult = false,
    List<FocusSession>? history,
    int? selectedDurationSeconds,
    String? selectedActivityType,
    DateTime? now,
    bool? isBusy,
    Object? error,
    bool clearError = false,
  }) => StudyFocusState(
    session: clearSession ? null : session ?? this.session,
    result: clearResult ? null : result ?? this.result,
    history: history ?? this.history,
    selectedDurationSeconds:
        selectedDurationSeconds ?? this.selectedDurationSeconds,
    selectedActivityType: selectedActivityType ?? this.selectedActivityType,
    now: now ?? this.now,
    isBusy: isBusy ?? this.isBusy,
    error: clearError ? null : error ?? this.error,
  );
}

class StudyFocusController extends AsyncNotifier<StudyFocusState> {
  final _uuid = const Uuid();
  Timer? _ticker;

  @override
  Future<StudyFocusState> build() async {
    final store = ref.read(studyFocusLocalStoreProvider);
    final history = await store.loadHistory();
    var active = await store.loadActive();
    FocusSession? result;
    final now = DateTime.now().toUtc();
    if (active != null &&
        active.status == FocusSessionStatus.running &&
        active.remainingAt(now) <= 0) {
      result = active.finishAt(now, early: false);
      await store.appendHistory(result);
      await store.clearActive();
      active = null;
    }
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    ref.onDispose(() => _ticker?.cancel());
    if (active?.status == FocusSessionStatus.running) {
      unawaited(ref.read(studyFocusAudioProvider).play());
      unawaited(
        ref
            .read(studyFocusNotificationServiceProvider)
            .schedule(now.add(Duration(seconds: active!.remainingAt(now)))),
      );
    }
    unawaited(
      _syncStoredSessions(
        active,
        result == null ? history : <FocusSession>[result, ...history],
      ),
    );
    return StudyFocusState(
      session: active,
      result: result,
      history: result == null ? history : <FocusSession>[result, ...history],
      selectedDurationSeconds: 25 * 60,
      selectedActivityType: '背单词',
      now: now,
      isBusy: false,
    );
  }

  void setDuration(int seconds) {
    final current = state.asData?.value;
    if (current == null || current.session != null) return;
    state = AsyncData(
      current.copyWith(selectedDurationSeconds: seconds, clearError: true),
    );
  }

  void setActivityType(String type) {
    final current = state.asData?.value;
    if (current == null || current.session != null) return;
    state = AsyncData(
      current.copyWith(selectedActivityType: type, clearError: true),
    );
  }

  Future<void> start({String shortGoal = ''}) async {
    final current = state.asData?.value;
    if (current == null || current.session != null || current.isBusy) return;
    final now = DateTime.now().toUtc();
    final session = FocusSession.start(
      sessionId: _uuid.v4(),
      activityType: current.selectedActivityType,
      shortGoal: shortGoal.trim(),
      plannedDurationSeconds: current.selectedDurationSeconds,
      now: now,
    );
    state = AsyncData(current.copyWith(isBusy: true, clearError: true));
    try {
      await ref.read(studyFocusLocalStoreProvider).saveActive(session);
      await ref
          .read(studyFocusNotificationServiceProvider)
          .schedule(now.add(Duration(seconds: session.plannedDurationSeconds)));
      await ref.read(studyFocusAudioProvider).play();
      state = AsyncData(
        current.copyWith(
          session: session,
          clearResult: true,
          now: now,
          isBusy: false,
          clearError: true,
        ),
      );
      unawaited(_syncCreate(session));
    } on Object catch (error, stackTrace) {
      debugPrint('Study focus start failed: $error');
      debugPrintStack(stackTrace: stackTrace);
      state = AsyncData(current.copyWith(isBusy: false, error: error));
    }
  }

  Future<void> pause() async {
    final current = state.asData?.value;
    final session = current?.session;
    if (current == null ||
        session == null ||
        !current.isRunning ||
        current.isBusy) {
      return;
    }
    final paused = session.pauseAt(DateTime.now().toUtc());
    state = AsyncData(current.copyWith(session: paused, isBusy: true));
    try {
      await ref.read(studyFocusLocalStoreProvider).saveActive(paused);
      await ref.read(studyFocusNotificationServiceProvider).cancel();
      await ref.read(studyFocusAudioProvider).pause();
      state = AsyncData(
        (state.asData?.value ?? current).copyWith(
          isBusy: false,
          clearError: true,
        ),
      );
      unawaited(_syncUpdate(paused));
    } on Object catch (error) {
      state = AsyncData(
        (state.asData?.value ?? current).copyWith(isBusy: false, error: error),
      );
    }
  }

  Future<void> resume() async {
    final current = state.asData?.value;
    final session = current?.session;
    if (current == null ||
        session == null ||
        !current.isPaused ||
        current.isBusy) {
      return;
    }
    final now = DateTime.now().toUtc();
    final resumed = session.resumeAt(now);
    state = AsyncData(current.copyWith(session: resumed, isBusy: true));
    try {
      await ref.read(studyFocusLocalStoreProvider).saveActive(resumed);
      await ref
          .read(studyFocusNotificationServiceProvider)
          .schedule(now.add(Duration(seconds: resumed.remainingAt(now))));
      await ref.read(studyFocusAudioProvider).play();
      state = AsyncData(
        (state.asData?.value ?? current).copyWith(
          now: now,
          isBusy: false,
          clearError: true,
        ),
      );
      unawaited(_syncUpdate(resumed));
    } on Object catch (error) {
      state = AsyncData(
        (state.asData?.value ?? current).copyWith(isBusy: false, error: error),
      );
    }
  }

  Future<void> finish({bool early = true}) async {
    final current = state.asData?.value;
    final session = current?.session;
    if (current == null || session == null || current.isBusy) return;
    final finished = session.finishAt(DateTime.now().toUtc(), early: early);
    state = AsyncData(current.copyWith(isBusy: true));
    try {
      final store = ref.read(studyFocusLocalStoreProvider);
      await store.appendHistory(finished);
      await store.clearActive();
      await ref.read(studyFocusNotificationServiceProvider).cancel();
      await ref.read(studyFocusAudioProvider).stop();
      final history = <FocusSession>[finished, ...current.history];
      state = AsyncData(
        current.copyWith(
          clearSession: true,
          result: finished,
          history: history,
          now: DateTime.now().toUtc(),
          isBusy: false,
          clearError: true,
        ),
      );
      unawaited(_syncUpdate(finished));
    } on Object catch (error) {
      state = AsyncData(current.copyWith(isBusy: false, error: error));
    }
  }

  void dismissResult() {
    final current = state.asData?.value;
    if (current == null) return;
    state = AsyncData(current.copyWith(clearResult: true, clearError: true));
  }

  void _tick() {
    final current = state.asData?.value;
    final session = current?.session;
    if (current == null || session == null) return;
    final now = DateTime.now().toUtc();
    state = AsyncData(current.copyWith(now: now));
    if (session.status == FocusSessionStatus.running &&
        session.remainingAt(now) <= 0 &&
        !current.isBusy) {
      unawaited(finish(early: false));
    }
  }

  Future<void> _syncCreate(FocusSession session) async {
    try {
      await ref.read(studyFocusApiProvider).createSession(session);
    } on Object {
      // The local timer remains authoritative while offline.
    }
  }

  Future<void> _syncUpdate(FocusSession session) async {
    try {
      await ref.read(studyFocusApiProvider).updateSession(session);
    } on Object {
      // A later sync pass can reconcile local history without blocking the UI.
    }
  }

  Future<void> _syncStoredSessions(
    FocusSession? active,
    List<FocusSession> history,
  ) async {
    final sessions = <FocusSession>[?active, ...history.take(20)];
    for (final session in sessions) {
      try {
        final api = ref.read(studyFocusApiProvider);
        await api.createSession(session);
        if (session.status != FocusSessionStatus.running ||
            session.elapsedSeconds > 0) {
          await api.updateSession(session);
        }
      } on Object {
        return;
      }
    }
  }
}

final studyFocusControllerProvider =
    AsyncNotifierProvider<StudyFocusController, StudyFocusState>(
      StudyFocusController.new,
    );
