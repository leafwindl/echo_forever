import 'package:echo_app/features/study_focus/data/study_focus_local_store.dart';
import 'package:echo_app/features/study_focus/domain/focus_session.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('appendHistory keeps the newest version of a session once', () async {
    final store = StudyFocusLocalStore();
    final start = DateTime.utc(2026, 8, 11, 9);
    final session = FocusSession.start(
      sessionId: 'session-1',
      activityType: '阅读',
      shortGoal: '',
      plannedDurationSeconds: 25 * 60,
      now: start,
    );
    final completed = session.finishAt(
      start.add(const Duration(seconds: 90)),
      early: false,
    );

    await store.appendHistory(session);
    await store.appendHistory(completed);

    final history = await store.loadHistory();
    expect(history, hasLength(1));
    expect(history.single.status, FocusSessionStatus.completed);
    expect(history.single.elapsedSeconds, 90);
  });

  test(
    'corrupt active state is removed while valid history survives',
    () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'study_focus.active_session': '{bad json',
        'study_focus.history': <String>['{bad history'],
      });
      final store = StudyFocusLocalStore();

      expect(await store.loadActive(), isNull);
      expect(await store.loadHistory(), isEmpty);
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.containsKey('study_focus.active_session'), isFalse);
    },
  );
}
