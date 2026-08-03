import 'package:dio/dio.dart';
import 'package:echo_app/core/errors/app_exception.dart';

class ErrorInterceptor extends Interceptor {
  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    handler.next(err.copyWith(error: AppException.fromDio(err)));
  }
}
