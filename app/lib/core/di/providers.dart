import 'package:dio/dio.dart';
import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/auth_session/session_events.dart';
import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/config/app_config.dart';
import 'package:echo_app/core/errors/error_code.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/interceptors/auth_interceptor.dart';
import 'package:echo_app/core/network/interceptors/error_interceptor.dart';
import 'package:echo_app/core/network/interceptors/request_id_interceptor.dart';
import 'package:echo_app/core/network/interceptors/safe_log_interceptor.dart';
import 'package:echo_app/core/network/token_refresh_coordinator.dart';
import 'package:echo_app/core/observability/app_logger.dart';
import 'package:echo_app/core/routing/pending_route_store.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/auth/data/auth_api.dart';
import 'package:echo_app/features/auth/data/auth_repository_impl.dart';
import 'package:echo_app/features/auth/domain/auth_repository.dart';
import 'package:echo_app/features/auth/domain/auth_session.dart';
import 'package:echo_app/features/letters/data/letters_api.dart';
import 'package:echo_app/features/letters/data/letters_repository.dart';
import 'package:echo_app/features/memory/data/memory_api.dart';
import 'package:echo_app/features/memory/data/memory_repository.dart';
import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/data/persona_repository.dart';
import 'package:echo_app/features/stickers/data/stickers_api.dart';
import 'package:echo_app/features/stickers/data/stickers_repository.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final appConfigProvider = Provider<AppConfig>((ref) {
  return AppConfig.fromEnvironment();
});

final publicDioProvider = Provider<Dio>((ref) {
  return _createDio(ref, authenticated: false);
});

final publicDioClientProvider = Provider<DioClient>((ref) {
  return DioClient(ref.watch(publicDioProvider));
});

final tokenRefreshCoordinatorProvider = Provider<TokenRefreshCoordinator>((
  ref,
) {
  return TokenRefreshCoordinator(
    readSession: () => ref.read(sessionControllerProvider).asData?.value,
    refreshSession: (refreshToken, deviceId) async {
      final session = await ref
          .read(authRepositoryProvider)
          .refresh(refreshToken: refreshToken, deviceId: deviceId);
      return _toSnapshot(session);
    },
    persistSession: (snapshot) async {
      await ref.read(sessionControllerProvider.notifier).establish(snapshot);
      ref.read(sessionControllerProvider.notifier).markOnline();
    },
    clearSession: (serverCode) async {
      ref.read(pendingRouteStoreProvider.notifier).clear();
      await ref
          .read(sessionControllerProvider.notifier)
          .signOut(_sessionEndReason(serverCode));
    },
    markSessionOffline: () {
      ref.read(sessionControllerProvider.notifier).markTemporarilyOffline();
    },
  );
});

final authenticatedDioProvider = Provider<Dio>((ref) {
  return _createDio(ref, authenticated: true);
});

final authenticatedDioClientProvider = Provider<DioClient>((ref) {
  return DioClient(ref.watch(authenticatedDioProvider));
});

final authApiProvider = Provider<AuthApi>((ref) {
  return AuthApi(
    ref.watch(publicDioClientProvider),
    ref.watch(authenticatedDioClientProvider),
  );
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepositoryImpl(
    ref.watch(authApiProvider),
    ref.watch(secureStoreProvider),
  );
});

final personaApiProvider = Provider<PersonaApi>((ref) {
  return PersonaApi(ref.watch(authenticatedDioClientProvider));
});

final personaRepositoryProvider = Provider<PersonaRepository>((ref) {
  return PersonaRepositoryImpl(ref.watch(personaApiProvider));
});

final memoryApiProvider = Provider<MemoryApi>((ref) {
  return MemoryApi(ref.watch(authenticatedDioClientProvider));
});

final memoryRepositoryProvider = Provider<MemoryRepository>((ref) {
  return MemoryRepositoryImpl(ref.watch(memoryApiProvider));
});

final stickersApiProvider = Provider<StickersApi>((ref) {
  return StickersApi(ref.watch(authenticatedDioClientProvider));
});

final stickersRepositoryProvider = Provider<StickersRepository>((ref) {
  return StickersRepositoryImpl(ref.watch(stickersApiProvider));
});

final lettersApiProvider = Provider<LettersApi>((ref) {
  return LettersApi(ref.watch(authenticatedDioClientProvider));
});

final lettersRepositoryProvider = Provider<LettersRepository>((ref) {
  return LettersRepositoryImpl(ref.watch(lettersApiProvider));
});

Dio _createDio(Ref ref, {required bool authenticated}) {
  final config = ref.watch(appConfigProvider);
  final dio = Dio(
    BaseOptions(
      baseUrl: config.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      sendTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 60),
      contentType: Headers.jsonContentType,
      responseType: ResponseType.json,
      headers: const <String, Object>{'Accept': Headers.jsonContentType},
    ),
  );
  dio.interceptors.add(
    RequestIdInterceptor(
      appVersion: config.appVersion,
      platform: defaultTargetPlatform.name,
    ),
  );
  if (authenticated) {
    dio.interceptors.add(
      AuthInterceptor(
        dio: dio,
        readSession: () => ref.read(sessionControllerProvider).asData?.value,
        refreshCoordinator: ref.watch(tokenRefreshCoordinatorProvider),
      ),
    );
  }
  dio.interceptors
    ..add(SafeLogInterceptor(AppLogger('EchoHttp')))
    ..add(ErrorInterceptor());
  return dio;
}

SessionSnapshot _toSnapshot(AuthSession session) {
  return SessionSnapshot.authenticated(
    userId: session.userId,
    accessToken: session.accessToken,
    refreshToken: session.refreshToken,
    tokenType: session.tokenType,
    accessExpiresAt: session.accessExpiresAt,
    refreshExpiresAt: session.refreshExpiresAt,
    deviceId: session.deviceId,
  );
}

SessionEndReason _sessionEndReason(String? serverCode) {
  return switch (serverCode) {
    ErrorCode.refreshExpired => SessionEndReason.refreshExpired,
    ErrorCode.refreshReused => SessionEndReason.refreshReused,
    ErrorCode.userDisabled => SessionEndReason.userDisabled,
    _ => SessionEndReason.refreshInvalid,
  };
}
