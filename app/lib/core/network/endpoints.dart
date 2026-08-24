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
  static const devices = '/devices';
  static const devicePairingClaim = '/devices/pairings/claim';

  static String proactiveSchedule(String scheduleId) =>
      '/proactive/schedules/${Uri.encodeComponent(scheduleId)}';

  static String studyFocusSession(String sessionId) =>
      '$studyFocusSessions/${Uri.encodeComponent(sessionId)}';

  static String device(String deviceId) =>
      '$devices/${Uri.encodeComponent(deviceId)}';

  static String deviceCredentialRotate(String deviceId) =>
      '${device(deviceId)}/credentials/rotate';

  static String deviceSpeaker(String deviceId) =>
      '${device(deviceId)}/speaker';

  static String deviceSpeakerEnrollment(String deviceId) =>
      '${deviceSpeaker(deviceId)}/enrollment';
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
