import 'dart:ui';

import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';

class RequestIdInterceptor extends Interceptor {
  RequestIdInterceptor({
    required this.appVersion,
    required this.platform,
    this.uuid = const Uuid(),
  });

  final String appVersion;
  final String platform;
  final Uuid uuid;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers.putIfAbsent('X-Request-ID', uuid.v4);
    options.headers.putIfAbsent('X-App-Version', () => appVersion);
    options.headers.putIfAbsent('X-Platform', () => platform);
    options.headers.putIfAbsent(
      'Accept-Language',
      () => PlatformDispatcher.instance.locale.toLanguageTag(),
    );
    handler.next(options);
  }
}
