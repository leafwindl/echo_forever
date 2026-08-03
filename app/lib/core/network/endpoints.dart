class Endpoints {
  const Endpoints._();

  static const phoneLogin = '/login/phone';
  static const verifyLogin = '/login/verify';
  static const refreshLogin = '/login/refresh';
  static const logout = '/login/logout';
  static const health = '/health';

  static const publicPaths = <String>{
    phoneLogin,
    verifyLogin,
    refreshLogin,
    health,
  };
}
