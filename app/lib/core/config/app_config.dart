import 'package:echo_app/core/config/app_environment.dart';

class AppConfig {
  const AppConfig({
    required this.environment,
    required this.baseUrl,
    required this.appVersion,
  });

  factory AppConfig.fromEnvironment() {
    const isReleaseBuild = bool.fromEnvironment('dart.vm.product');
    const environmentValue = String.fromEnvironment(
      'ECHO_ENV',
      defaultValue: isReleaseBuild ? 'production' : 'development',
    );
    const injectedBaseUrl = String.fromEnvironment('ECHO_BASE_URL');
    const appVersion = String.fromEnvironment(
      'APP_VERSION',
      defaultValue: '0.1.0',
    );
    final environment = AppEnvironment.parse(environmentValue);
    final defaultBaseUrl =
        !isReleaseBuild && environment == AppEnvironment.development
        ? 'http://127.0.0.1:8000'
        : 'https://api.echoaiforever.cn';
    var baseUrl = (injectedBaseUrl.isEmpty ? defaultBaseUrl : injectedBaseUrl)
        .replaceFirst(RegExp(r'/+$'), '');
    final parsedInjectedUrl = Uri.tryParse(baseUrl);
    if (isReleaseBuild &&
        (parsedInjectedUrl?.host == 'localhost' ||
            parsedInjectedUrl?.host == '127.0.0.1')) {
      baseUrl = 'https://api.echoaiforever.cn';
    }
    final uri = Uri.tryParse(baseUrl);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      throw StateError('ECHO_BASE_URL must be an absolute HTTP(S) URL.');
    }

    return AppConfig(
      environment: environment,
      baseUrl: baseUrl,
      appVersion: appVersion,
    );
  }

  final AppEnvironment environment;
  final String baseUrl;
  final String appVersion;
}
