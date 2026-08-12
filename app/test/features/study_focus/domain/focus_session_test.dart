import 'package:echo_app/features/study_focus/domain/focus_session.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final start = DateTime.utc(2026, 8, 11, 9);

  test(
    'running session calculates elapsed and remaining from active start',
    () {
      final session = FocusSession.start(
        sessionId: 'session-1',
        activityType: '阅读',
        shortGoal: '完成一节',
        plannedDurationSeconds: 25 * 60,
        now: start,
      );

      expect(session.elapsedAt(start.add(const Duration(seconds: 37))), 37);
      expect(
        session.remainingAt(start.add(const Duration(seconds: 37))),
        25 * 60 - 37,
      );
    },
  );

  test('pause freezes elapsed time and resume starts a new active segment', () {
    final running = FocusSession.start(
      sessionId: 'session-2',
      activityType: '刷题',
      shortGoal: '',
      plannedDurationSeconds: 25 * 60,
      now: start,
    );
    final paused = running.pauseAt(start.add(const Duration(seconds: 42)));
    final resumed = paused.resumeAt(start.add(const Duration(minutes: 2)));

    expect(paused.status, FocusSessionStatus.paused);
    expect(paused.elapsedAt(start.add(const Duration(minutes: 5))), 42);
    expect(
      resumed.elapsedAt(start.add(const Duration(minutes: 2, seconds: 18))),
      60,
    );
  });

  test('finish clamps elapsed time and records terminal status', () {
    final running = FocusSession.start(
      sessionId: 'session-3',
      activityType: '看课',
      shortGoal: '',
      plannedDurationSeconds: 60,
      now: start,
    );
    final completed = running.finishAt(
      start.add(const Duration(seconds: 90)),
      early: false,
    );
    final early = running.finishAt(
      start.add(const Duration(seconds: 12)),
      early: true,
    );

    expect(completed.elapsedSeconds, 60);
    expect(completed.status, FocusSessionStatus.completed);
    expect(completed.endedAt, start.add(const Duration(seconds: 90)));
    expect(early.elapsedSeconds, 12);
    expect(early.status, FocusSessionStatus.endedEarly);
  });

  test('session JSON round trips pause state', () {
    final session = FocusSession.start(
      sessionId: 'session-4',
      activityType: '背单词',
      shortGoal: '单元三',
      plannedDurationSeconds: 50 * 60,
      now: start,
    ).pauseAt(start.add(const Duration(seconds: 9)));

    final restored = FocusSession.fromJson(session.toJson());

    expect(restored.sessionId, session.sessionId);
    expect(restored.activityType, session.activityType);
    expect(restored.shortGoal, session.shortGoal);
    expect(restored.elapsedSeconds, 9);
    expect(restored.status, FocusSessionStatus.paused);
    expect(restored.activeStartedAt, isNull);
  });
}
