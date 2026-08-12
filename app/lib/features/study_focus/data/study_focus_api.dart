import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';
import 'package:echo_app/features/study_focus/domain/focus_session.dart';

class StudyFocusApi {
  const StudyFocusApi(this._client);

  final DioClient _client;

  Future<void> createSession(FocusSession session) async {
    await _client.post<Map<String, dynamic>>(
      Endpoints.studyFocusSessions,
      data: <String, dynamic>{
        'session_id': session.sessionId,
        'activity_type': session.activityType,
        'short_goal': session.shortGoal,
        'planned_duration_seconds': session.plannedDurationSeconds,
        'started_at': session.startedAt.toIso8601String(),
        'timezone': 'Asia/Shanghai',
      },
    );
  }

  Future<void> updateSession(FocusSession session) async {
    final now = DateTime.now().toUtc();
    final occurredAt = session.endedAt ?? now;
    await _client.put<Map<String, dynamic>>(
      Endpoints.studyFocusSession(session.sessionId),
      data: <String, dynamic>{
        'status': switch (session.status) {
          FocusSessionStatus.running => 'running',
          FocusSessionStatus.paused => 'paused',
          FocusSessionStatus.completed => 'completed',
          FocusSessionStatus.endedEarly => 'ended_early',
        },
        'actual_duration_seconds': session.elapsedAt(now),
        'occurred_at': occurredAt.toIso8601String(),
      },
    );
  }
}
