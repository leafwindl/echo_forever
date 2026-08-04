class Endpoints {
  const Endpoints._();

  static const phoneLogin = '/login/phone';
  static const verifyLogin = '/login/verify';
  static const refreshLogin = '/login/refresh';
  static const logout = '/login/logout';
  static const health = '/health';
  static const pushTokensMe = '/push/tokens/me';

  static String pushTokenForDevice(String deviceId) =>
      '/push/tokens/me/${Uri.encodeComponent(deviceId)}';

  static const publicPaths = <String>{
    phoneLogin,
    verifyLogin,
    refreshLogin,
    health,
  };
}
