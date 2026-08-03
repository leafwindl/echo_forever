import 'package:dio/dio.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('prefers auth code and parses tracing headers', () {
    final exception = AppException.fromResponse(
      Response<Map<String, dynamic>>(
        requestOptions: RequestOptions(path: '/login/verify'),
        statusCode: 429,
        data: <String, dynamic>{
          'code': 'AUTH_VERIFY_RATE_LIMITED',
          'detail': '验证请求过于频繁',
          'request_id': 'request-id',
        },
        headers: Headers.fromMap(<String, List<String>>{
          'Retry-After': <String>['12'],
        }),
      ),
    );

    expect(exception.kind, AppExceptionKind.rateLimited);
    expect(exception.serverCode, 'AUTH_VERIFY_RATE_LIMITED');
    expect(exception.requestId, 'request-id');
    expect(exception.retryAfter, const Duration(seconds: 12));
    expect(exception.isRetryable, isTrue);
  });

  test('tolerates FastAPI validation detail arrays', () {
    final exception = AppException.fromResponse(
      Response<List<Object?>>(
        requestOptions: RequestOptions(path: '/example'),
        statusCode: 422,
        data: <Object?>[
          <String, Object?>{'msg': 'Field required'},
        ],
      ),
    );

    expect(exception.kind, AppExceptionKind.validation);
    expect(exception.detail, 'Field required');
  });
}
