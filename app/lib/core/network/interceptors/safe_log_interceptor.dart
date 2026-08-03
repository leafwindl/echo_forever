import 'package:dio/dio.dart';
import 'package:echo_app/core/observability/app_logger.dart';

class SafeLogInterceptor extends Interceptor {
  SafeLogInterceptor(this._logger);

  static const _startedAtKey = 'safeLogStartedAt';
  final AppLogger _logger;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.extra[_startedAtKey] = DateTime.now();
    _logger.info(
      'HTTP start method=${options.method} path=${options.path} '
      'request_id=${options.headers['X-Request-ID']}',
    );
    handler.next(options);
  }

  @override
  void onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) {
    _logger.info(
      'HTTP complete method=${response.requestOptions.method} '
      'path=${response.requestOptions.path} status=${response.statusCode} '
      'duration_ms=${_duration(response.requestOptions)} '
      'request_id=${response.headers.value('X-Request-ID') ?? response.requestOptions.headers['X-Request-ID']}',
    );
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    _logger.warning(
      'HTTP failed method=${err.requestOptions.method} '
      'path=${err.requestOptions.path} status=${err.response?.statusCode} '
      'duration_ms=${_duration(err.requestOptions)} '
      'request_id=${err.response?.headers.value('X-Request-ID') ?? err.requestOptions.headers['X-Request-ID']} '
      'category=${err.type.name}',
    );
    handler.next(err);
  }

  int _duration(RequestOptions options) {
    final startedAt = options.extra[_startedAtKey];
    return startedAt is DateTime
        ? DateTime.now().difference(startedAt).inMilliseconds
        : 0;
  }
}
