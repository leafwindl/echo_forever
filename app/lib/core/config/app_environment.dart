enum AppEnvironment {
  development,
  staging,
  production;

  static AppEnvironment parse(String value) {
    return AppEnvironment.values.firstWhere(
      (environment) => environment.name == value.toLowerCase(),
      orElse: () => AppEnvironment.development,
    );
  }
}
