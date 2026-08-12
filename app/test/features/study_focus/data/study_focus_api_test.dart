import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/study_focus/data/study_focus_api.dart';
import 'package:echo_app/features/study_focus/domain/focus_session.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('terminal sync uses the original endedAt as occurred_at', () async {
    late RequestOptions captured;
    final dio = Dio()
      ..httpClientAdapter = _Adapter((request) {
        captured = request;
        return ResponseBody.fromString(
          jsonEncode(<String, dynamic>{}),
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
        );
      });
    final api = StudyFocusApi(DioClient(dio));
    final endedAt = DateTime.utc(2026, 8, 11, 9, 25);
    final session = FocusSession.start(
      sessionId: 'session-1',
      activityType: '阅读',
      shortGoal: '',
      plannedDurationSeconds: 25 * 60,
      now: DateTime.utc(2026, 8, 11, 9),
    ).finishAt(endedAt, early: false);

    await api.updateSession(session);

    expect(captured.method, 'PUT');
    expect(captured.path, '/study-focus/sessions/session-1');
    expect(captured.data['status'], 'completed');
    expect(captured.data['occurred_at'], endedAt.toIso8601String());
  });
}

class _Adapter implements HttpClientAdapter {
  _Adapter(this.handler);

  final ResponseBody Function(RequestOptions request) handler;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async => handler(options);

  @override
  void close({bool force = false}) {}
}
