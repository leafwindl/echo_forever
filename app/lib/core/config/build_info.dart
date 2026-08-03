class BuildInfo {
  const BuildInfo._();

  static const buildNumber = String.fromEnvironment(
    'BUILD_NUMBER',
    defaultValue: '1',
  );
  static const commitSha = String.fromEnvironment(
    'COMMIT_SHA',
    defaultValue: 'local',
  );
}
