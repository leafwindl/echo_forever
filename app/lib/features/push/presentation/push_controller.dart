import 'dart:async';

import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/routing/pending_route_store.dart';
import 'package:echo_app/features/push/data/push_api.dart';
import 'package:echo_app/features/push/domain/push_notification.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const _firebaseNotConfigured = 'Firebase 项目尚未配置，FCM 暂不可用';

final pushApiProvider = Provider<PushApi>((ref) {
  return PushApi(ref.watch(authenticatedDioClientProvider));
});

final pushControllerProvider = NotifierProvider<PushController, PushState>(
  PushController.new,
);

class PushState {
  const PushState({
    this.initialized = false,
    this.permission,
    this.error,
    this.pending,
    this.foregroundNotification,
  });

  final bool initialized;
  final AuthorizationStatus? permission;
  final String? error;
  final PushNotification? pending;
  final PushNotification? foregroundNotification;

  bool get isEnabled =>
      permission == AuthorizationStatus.authorized ||
      permission == AuthorizationStatus.provisional;

  PushState copyWith({
    bool? initialized,
    AuthorizationStatus? permission,
    String? error,
    bool clearError = false,
    PushNotification? pending,
    bool clearPending = false,
    PushNotification? foregroundNotification,
    bool clearForegroundNotification = false,
  }) => PushState(
    initialized: initialized ?? this.initialized,
    permission: permission ?? this.permission,
    error: clearError ? null : error ?? this.error,
    pending: clearPending ? null : pending ?? this.pending,
    foregroundNotification: clearForegroundNotification
        ? null
        : foregroundNotification ?? this.foregroundNotification,
  );
}

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
  } on Object {
    // Firebase options are supplied by google-services.json after release setup.
  }
}

class PushController extends Notifier<PushState> {
  StreamSubscription<String>? _tokenSubscription;
  StreamSubscription<RemoteMessage>? _openedSubscription;
  StreamSubscription<RemoteMessage>? _messageSubscription;
  bool _firebaseAvailable = false;
  String? _lastRegistrationKey;
  final Set<String> _handledClickIds = <String>{};
  final Set<String> _seenForegroundIds = <String>{};
  Future<void>? _initializationFuture;

  @override
  PushState build() {
    ref.onDispose(() {
      unawaited(_tokenSubscription?.cancel());
      unawaited(_openedSubscription?.cancel());
      unawaited(_messageSubscription?.cancel());
    });
    return const PushState();
  }

  Future<void> initialize() {
    if (state.initialized) return Future<void>.value();
    final running = _initializationFuture;
    if (running != null) return running;
    final future = _initialize();
    _initializationFuture = future;
    return future.whenComplete(() => _initializationFuture = null);
  }

  Future<void> _initialize() async {
    try {
      await Firebase.initializeApp();
      _firebaseAvailable = true;
    } on Object {
      state = state.copyWith(initialized: true, error: _firebaseNotConfigured);
      return;
    }
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
    final messaging = FirebaseMessaging.instance;
    _tokenSubscription = messaging.onTokenRefresh.listen(_registerToken);
    _messageSubscription = FirebaseMessaging.onMessage.listen(
      (message) => _handleForegroundMessage(message),
    );
    _openedSubscription = FirebaseMessaging.onMessageOpenedApp.listen(
      (message) => handleMessage(message.data),
    );
    final initial = await messaging.getInitialMessage();
    if (initial != null) {
      handleMessage(initial.data);
    }
    final settings = await messaging.getNotificationSettings();
    state = state.copyWith(
      initialized: true,
      permission: settings.authorizationStatus,
    );
    final session = ref.read(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated ?? false) {
      final token = await messaging.getToken();
      if (token != null) await _registerToken(token);
    }
  }

  Future<void> requestPermission() async {
    if (!_firebaseAvailable) {
      await initialize();
      if (!_firebaseAvailable) return;
    }
    final settings = await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );
    state = state.copyWith(permission: settings.authorizationStatus);
    if (settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional) {
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) await _registerToken(token);
    }
  }

  void handleMessage(Map<String, dynamic> data) {
    final notification = PushNotification.fromData(data);
    if (notification == null) return;
    if (!_handledClickIds.add(notification.notificationId)) return;
    if (_handledClickIds.length > 64) {
      _handledClickIds.remove(_handledClickIds.first);
    }
    final previous = state.pending;
    if (previous?.notificationId == notification.notificationId) return;
    state = state.copyWith(pending: notification);
    ref
        .read(pendingRouteStoreProvider.notifier)
        .remember(notification.navigationLocation);
  }

  void _handleForegroundMessage(RemoteMessage message) {
    final notification = PushNotification.fromData(message.data);
    if (notification == null) return;
    if (!_seenForegroundIds.add(notification.notificationId)) {
      return;
    }
    if (_seenForegroundIds.length > 64) {
      _seenForegroundIds.remove(_seenForegroundIds.first);
    }
    state = state.copyWith(foregroundNotification: notification);
  }

  void dismissForegroundNotification() {
    state = state.copyWith(clearForegroundNotification: true);
  }

  Future<void> registerCurrentToken() async {
    if (!_firebaseAvailable) {
      await initialize();
    }
    if (!_firebaseAvailable) return;
    final token = await FirebaseMessaging.instance.getToken();
    if (token != null) {
      await _registerToken(token);
    }
  }

  PushNotification? takePending() {
    final value = state.pending;
    state = state.copyWith(clearPending: true);
    ref.read(pendingRouteStoreProvider.notifier).clear();
    return value;
  }

  Future<void> unregisterCurrentDevice() async {
    final snapshot = ref.read(sessionControllerProvider).asData?.value;
    final deviceId = snapshot?.deviceId;
    if (deviceId == null) return;
    try {
      await ref.read(pushApiProvider).unregisterToken(deviceId);
    } on Object {
      // Local sign-out must not be blocked by an unavailable push endpoint.
    }
  }

  Future<void> _registerToken(String token) async {
    if (!_firebaseAvailable) return;
    final snapshot = ref.read(sessionControllerProvider).asData?.value;
    if (!(snapshot?.isAuthenticated ?? false)) return;
    final config = ref.read(appConfigProvider);
    final deviceId = snapshot!.deviceId!;
    final registrationKey =
        '${snapshot.userId}|$deviceId|$token|${config.appVersion}|${config.environment.name}';
    if (registrationKey == _lastRegistrationKey) return;
    try {
      await ref
          .read(pushApiProvider)
          .registerToken(
            deviceId: deviceId,
            platform: defaultTargetPlatform.name,
            provider: 'fcm',
            token: token,
            appVersion: config.appVersion,
            environment: config.environment.name,
            locale: PlatformDispatcher.instance.locale.toLanguageTag(),
          );
      _lastRegistrationKey = registrationKey;
    } on Object {
      // Endpoint is intentionally optional until Echo-backend adds push_tokens.
    }
  }
}
