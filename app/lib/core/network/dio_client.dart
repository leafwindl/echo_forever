import 'package:dio/dio.dart';
import 'package:echo_app/core/errors/app_exception.dart';

class DioClient {
  const DioClient(this.dio);

  final Dio dio;

  Future<Response<T>> post<T>(
    String path, {
    Object? data,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      return await dio.post<T>(
        path,
        data: data,
        options: options,
        cancelToken: cancelToken,
      );
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }
}
