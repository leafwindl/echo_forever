import 'package:dio/dio.dart';
import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/network/endpoints.dart';
import 'package:echo_app/core/network/token_refresh_coordinator.dart';

typedef SessionReader = SessionSnapshot? Function();

class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required this.dio,
    required this.readSession,
    required this.refreshCoordinator,
  });

  static const _retryCountKey = 'authRetryCount';
  final Dio dio;
  final SessionReader readSession;
  final TokenRefreshCoordinator refreshCoordinator;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (_isPublic(options.path)) {
      handler.next(options);
      return;
    }
    var snapshot = readSession();
    if (snapshot?.needsRefresh() ?? false) {
      try {
        snapshot = await refreshCoordinator.refresh();
      } on AppException catch (error) {
        snapshot = readSession();
        if (!(snapshot?.accessTokenIsUsable ?? false)) {
          handler.reject(
            DioException(
              requestOptions: options,
              error: error,
              type: DioExceptionType.unknown,
            ),
          );
          return;
        }
      }
    }
    if (snapshot?.isAuthenticated ?? false) {
      options.headers['Authorization'] =
          '${snapshot!.tokenType} ${snapshot.accessToken}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final request = err.requestOptions;
    final retryCount = request.extra[_retryCountKey] as int? ?? 0;
    if (err.response?.statusCode != 401 ||
        _isPublic(request.path) ||
        retryCount >= 1) {
      handler.next(err);
      return;
    }
    try {
      final refreshed = await refreshCoordinator.refresh(force: true);
      if (refreshed == null) {
        handler.next(err);
        return;
      }
      final headers = Map<String, dynamic>.from(request.headers)
        ..['Authorization'] = '${refreshed.tokenType} ${refreshed.accessToken}';
      final extra = Map<String, dynamic>.from(request.extra)
        ..[_retryCountKey] = retryCount + 1;
      final response = await dio.fetch<dynamic>(
        request.copyWith(headers: headers, extra: extra),
      );
      handler.resolve(response);
    } on Object {
      handler.next(err);
    }
  }

  bool _isPublic(String path) {
    final normalized = Uri.parse(path).path;
    return Endpoints.publicPaths.contains(normalized);
  }
}
