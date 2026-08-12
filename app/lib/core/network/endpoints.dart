class Endpoints {
  const Endpoints._();

  static const phoneLogin = '/login/phone';
  static const verifyLogin = '/login/verify';
  static const refreshLogin = '/login/refresh';
  static const logout = '/login/logout';
  static const health = '/health';
  static const pushTokensMe = '/push/tokens/me';
  static const proactivePreferences = '/proactive/preferences';
  static const proactiveSchedules = '/proactive/schedules';
  static const studyFocusSessions = '/study-focus/sessions';

  static String proactiveSchedule(String scheduleId) =>
      '/proactive/schedules/${Uri.encodeComponent(scheduleId)}';

  static String studyFocusSession(String sessionId) =>
      '$studyFocusSessions/${Uri.encodeComponent(sessionId)}';
  static const latestRelease = '/releases/latest';

  static String pushTokenForDevice(String deviceId) =>
      '/push/tokens/me/${Uri.encodeComponent(deviceId)}';

  static String releaseDownload(String releaseId) =>
      '/releases/${Uri.encodeComponent(releaseId)}/download';

  static const publicPaths = <String>{
    phoneLogin,
    verifyLogin,
    refreshLogin,
    health,
    latestRelease,
  };
}
