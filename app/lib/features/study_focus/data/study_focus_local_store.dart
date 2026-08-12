import 'dart:convert';

import 'package:echo_app/features/study_focus/domain/focus_session.dart';
import 'package:shared_preferences/shared_preferences.dart';

class StudyFocusLocalStore {
  static const _activeKey = 'study_focus.active_session';
  static const _historyKey = 'study_focus.history';

  Future<FocusSession?> loadActive() async {
    final preferences = await SharedPreferences.getInstance();
    final value = preferences.getString(_activeKey);
    if (value == null || value.isEmpty) return null;
    try {
      return FocusSession.fromJson(jsonDecode(value) as Map<String, dynamic>);
    } on Object {
      await preferences.remove(_activeKey);
      return null;
    }
  }

  Future<List<FocusSession>> loadHistory() async {
    final preferences = await SharedPreferences.getInstance();
    final values = preferences.getStringList(_historyKey) ?? const <String>[];
    final sessions = <FocusSession>[];
    for (final value in values) {
      try {
        sessions.add(
          FocusSession.fromJson(jsonDecode(value) as Map<String, dynamic>),
        );
      } on Object {
        // Ignore a single corrupt historical record and retain the rest.
      }
    }
    return sessions;
  }

  Future<void> saveActive(FocusSession session) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_activeKey, jsonEncode(session.toJson()));
  }

  Future<void> clearActive() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(_activeKey);
  }

  Future<void> appendHistory(FocusSession session) async {
    final preferences = await SharedPreferences.getInstance();
    final values = preferences.getStringList(_historyKey) ?? <String>[];
    values.removeWhere((value) {
      try {
        final json = jsonDecode(value) as Map<String, dynamic>;
        return json['session_id'] == session.sessionId;
      } on Object {
        return false;
      }
    });
    values.insert(0, jsonEncode(session.toJson()));
    if (values.length > 90) {
      values.removeRange(90, values.length);
    }
    await preferences.setStringList(_historyKey, values);
  }
}
