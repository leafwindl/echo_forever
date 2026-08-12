import 'dart:math' as math;

enum FocusSessionStatus { running, paused, completed, endedEarly }

class FocusSession {
  const FocusSession({
    required this.sessionId,
    required this.activityType,
    required this.shortGoal,
    required this.plannedDurationSeconds,
    required this.startedAt,
    required this.elapsedSeconds,
    required this.status,
    this.activeStartedAt,
    this.endedAt,
  });

  factory FocusSession.start({
    required String sessionId,
    required String activityType,
    required String shortGoal,
    required int plannedDurationSeconds,
    required DateTime now,
  }) {
    final startedAt = now.toUtc();
    return FocusSession(
      sessionId: sessionId,
      activityType: activityType,
      shortGoal: shortGoal,
      plannedDurationSeconds: plannedDurationSeconds,
      startedAt: startedAt,
      activeStartedAt: startedAt,
      elapsedSeconds: 0,
      status: FocusSessionStatus.running,
    );
  }

  factory FocusSession.fromJson(Map<String, dynamic> json) {
    return FocusSession(
      sessionId: json['session_id'] as String,
      activityType: json['activity_type'] as String? ?? '学习',
      shortGoal: json['short_goal'] as String? ?? '',
      plannedDurationSeconds: json['planned_duration_seconds'] as int,
      startedAt: DateTime.parse(json['started_at'] as String).toUtc(),
      activeStartedAt: (json['active_started_at'] as String?) == null
          ? null
          : DateTime.parse(json['active_started_at'] as String).toUtc(),
      elapsedSeconds: json['elapsed_seconds'] as int? ?? 0,
      status: FocusSessionStatus.values.firstWhere(
        (value) => value.name == json['status'],
        orElse: () => FocusSessionStatus.paused,
      ),
      endedAt: (json['ended_at'] as String?) == null
          ? null
          : DateTime.parse(json['ended_at'] as String).toUtc(),
    );
  }

  final String sessionId;
  final String activityType;
  final String shortGoal;
  final int plannedDurationSeconds;
  final DateTime startedAt;
  final DateTime? activeStartedAt;
  final int elapsedSeconds;
  final FocusSessionStatus status;
  final DateTime? endedAt;

  bool get isActive =>
      status == FocusSessionStatus.running ||
      status == FocusSessionStatus.paused;

  int elapsedAt(DateTime now) {
    if (status != FocusSessionStatus.running || activeStartedAt == null) {
      return math.min(elapsedSeconds, plannedDurationSeconds);
    }
    final runningSeconds = now.toUtc().difference(activeStartedAt!).inSeconds;
    return math.min(
      plannedDurationSeconds,
      math.max(0, elapsedSeconds + math.max(0, runningSeconds)),
    );
  }

  int remainingAt(DateTime now) =>
      math.max(0, plannedDurationSeconds - elapsedAt(now));

  FocusSession pauseAt(DateTime now) {
    if (status != FocusSessionStatus.running) return this;
    return FocusSession(
      sessionId: sessionId,
      activityType: activityType,
      shortGoal: shortGoal,
      plannedDurationSeconds: plannedDurationSeconds,
      startedAt: startedAt,
      activeStartedAt: null,
      elapsedSeconds: elapsedAt(now),
      status: FocusSessionStatus.paused,
      endedAt: endedAt,
    );
  }

  FocusSession resumeAt(DateTime now) {
    if (status != FocusSessionStatus.paused) return this;
    return FocusSession(
      sessionId: sessionId,
      activityType: activityType,
      shortGoal: shortGoal,
      plannedDurationSeconds: plannedDurationSeconds,
      startedAt: startedAt,
      activeStartedAt: now.toUtc(),
      elapsedSeconds: elapsedSeconds,
      status: FocusSessionStatus.running,
      endedAt: endedAt,
    );
  }

  FocusSession finishAt(DateTime now, {required bool early}) {
    final finishedElapsed = elapsedAt(now);
    return FocusSession(
      sessionId: sessionId,
      activityType: activityType,
      shortGoal: shortGoal,
      plannedDurationSeconds: plannedDurationSeconds,
      startedAt: startedAt,
      activeStartedAt: null,
      elapsedSeconds: finishedElapsed,
      status: early
          ? FocusSessionStatus.endedEarly
          : FocusSessionStatus.completed,
      endedAt: now.toUtc(),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'session_id': sessionId,
    'activity_type': activityType,
    'short_goal': shortGoal,
    'planned_duration_seconds': plannedDurationSeconds,
    'started_at': startedAt.toIso8601String(),
    'active_started_at': activeStartedAt?.toIso8601String(),
    'elapsed_seconds': elapsedSeconds,
    'status': status.name,
    'ended_at': endedAt?.toIso8601String(),
  };
}
