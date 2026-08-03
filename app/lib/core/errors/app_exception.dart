import 'dart:convert';

import 'package:dio/dio.dart';

enum AppExceptionKind {
  networkUnavailable,
  timeout,
  cancelled,
  badRequest,
  unauthorized,
  forbidden,
  notFound,
  requestInProgress,
  payloadTooLarge,
  validation,
  rateLimited,
  serverError,
  serviceUnavailable,
  unexpected,
}

class AppException implements Exception {
  const AppException({
    required this.kind,
    this.httpStatus,
    this.serverCode,
    this.detail,
    this.requestId,
    this.retryAfter,
    this.isRetryable = false,
  });

  factory AppException.fromDio(DioException error) {
    if (error.error is AppException) {
      return error.error! as AppException;
    }
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const AppException(
          kind: AppExceptionKind.timeout,
          isRetryable: true,
        );
      case DioExceptionType.cancel:
        return const AppException(kind: AppExceptionKind.cancelled);
      case DioExceptionType.connectionError:
      case DioExceptionType.badCertificate:
        return const AppException(
          kind: AppExceptionKind.networkUnavailable,
          isRetryable: true,
        );
      case DioExceptionType.badResponse:
        return AppException.fromResponse(error.response);
      case DioExceptionType.unknown:
        return const AppException(
          kind: AppExceptionKind.networkUnavailable,
          isRetryable: true,
        );
    }
  }

  factory AppException.fromResponse(Response<dynamic>? response) {
    final status = response?.statusCode;
    final body = response?.data;
    final map = body is Map
        ? Map<String, dynamic>.from(body)
        : const <String, dynamic>{};
    final code = map['code']?.toString();
    final detail = _parseDetail(map['detail'] ?? body);
    final requestId =
        map['request_id']?.toString() ??
        response?.headers.value('X-Request-ID');
    final retrySeconds = int.tryParse(
      response?.headers.value('Retry-After') ?? '',
    );
    final kind = switch (status) {
      400 || 410 || 423 => AppExceptionKind.badRequest,
      401 => AppExceptionKind.unauthorized,
      403 => AppExceptionKind.forbidden,
      404 => AppExceptionKind.notFound,
      409 => AppExceptionKind.requestInProgress,
      413 => AppExceptionKind.payloadTooLarge,
      422 => AppExceptionKind.validation,
      429 => AppExceptionKind.rateLimited,
      500 => AppExceptionKind.serverError,
      503 => AppExceptionKind.serviceUnavailable,
      _ => AppExceptionKind.unexpected,
    };

    return AppException(
      kind: kind,
      httpStatus: status,
      serverCode: code,
      detail: detail,
      requestId: requestId,
      retryAfter: retrySeconds == null ? null : Duration(seconds: retrySeconds),
      isRetryable:
          kind == AppExceptionKind.rateLimited ||
          kind == AppExceptionKind.serverError ||
          kind == AppExceptionKind.serviceUnavailable,
    );
  }

  final AppExceptionKind kind;
  final int? httpStatus;
  final String? serverCode;
  final String? detail;
  final String? requestId;
  final Duration? retryAfter;
  final bool isRetryable;

  static String? _parseDetail(Object? detail) {
    if (detail == null) {
      return null;
    }
    if (detail is String) {
      return detail;
    }
    if (detail is List) {
      final messages = detail
          .map(
            (item) => item is Map ? item['msg']?.toString() : item.toString(),
          )
          .whereType<String>()
          .where((message) => message.isNotEmpty)
          .toList(growable: false);
      return messages.isEmpty ? null : messages.join('; ');
    }
    try {
      return jsonEncode(detail);
    } on Object {
      return detail.toString();
    }
  }

  @override
  String toString() =>
      'AppException(kind: $kind, status: $httpStatus, code: $serverCode, '
      'requestId: $requestId)';
}
