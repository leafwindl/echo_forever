import 'dart:async';
import 'dart:convert';

import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/routing/pending_route_store.dart';
import 'package:echo_app/features/push/data/getui_push_gateway.dart';
import 'package:echo_app/features/push/data/push_api.dart';
import 'package:echo_app/features/push/domain/push_notification.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const _pushUnavailable = '当前设备暂不支持 Echo 系统通知';

final pushApiProvider = Provider<PushApi>((ref) {
  return PushApi(ref.watch(authenticatedDioClientProvider));
});

final pushGatewayProvider = Provider<PushGateway>((ref) {
  return GetuiPushGateway();
});

final pushControllerProvider = NotifierProvider<PushController, PushState>(
  PushController.new,
);

class PushState {
  const PushState({
    this.initialized = false,
    this.permission = PushPermissionStatus.unknown,
    this.error,
    this.pending,
    this.foregroundNotification,
  });

  final bool initialized;
  final PushPermissionStatus permission;
  final String? error;
  final PushNotification? pending;
  final PushNotification? foregroundNotification;

  bool get isEnabled => permission == PushPermissionStatus.authorized;

  PushState copyWith({
    bool? initialized,
    PushPermissionStatus? permission,
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

class PushController extends Notifier<PushState> {
  String? _clientId;
  String? _lastRegistrationKey;
  final Set<String> _handledClickIds = <String>{};
  final Set<String> _seenForegroundIds = <String>{};
  Future<void>? _initializationFuture;

  @override
  PushState build() => const PushState();

  Future<void> initialize() {
    final session = ref.read(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated != true) return Future<void>.value();
    if (state.initialized) return Future<void>.value();
    final running = _initializationFuture;
    if (running != null) return running;
    final future = _initialize();
    _initializationFuture = future;
    return future.whenComplete(() => _initializationFuture = null);
  }

  Future<void> _initialize() async {
    try {
      final gateway = ref.read(pushGatewayProvider);
      final permission = await gateway.initialize(
        PushGatewayCallbacks(
          onClientId: _registerClientId,
          onNotificationArrived: _handleForegroundEvent,
          onNotificationClicked: _handleClickedEvent,
          onPayload: _handleForegroundEvent,
        ),
      );
      state = state.copyWith(
        initialized: true,
        permission: permission,
        error: permission == PushPermissionStatus.unsupported
            ? _pushUnavailable
            : null,
        clearError: permission != PushPermissionStatus.unsupported,
      );
      _clientId = await gateway.clientId();
      if (_clientId != null) await _registerClientId(_clientId!);
    } on Object {
      state = state.copyWith(initialized: true, error: _pushUnavailable);
    }
  }

  Future<void> requestPermission() async {
    await initialize();
    if (!state.initialized) return;
    try {
      final permission = await ref.read(pushGatewayProvider).requestPermission();
      state = state.copyWith(
        permission: permission,
        error: permission == PushPermissionStatus.unsupported
            ? _pushUnavailable
            : null,
        clearError: permission != PushPermissionStatus.unsupported,
      );
      if (permission == PushPermissionStatus.authorized) {
        await registerCurrentToken();
      }
    } on Object {
      state = state.copyWith(error: '通知权限请求失败，请前往系统设置重试');
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

  void dismissForegroundNotification() {
    state = state.copyWith(clearForegroundNotification: true);
  }

  Future<void> registerCurrentToken() async {
    await initialize();
    final clientId = _clientId ?? await ref.read(pushGatewayProvider).clientId();
    if (clientId != null) await _registerClientId(clientId);
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
      _lastRegistrationKey = null;
    } on Object {
      // Local sign-out must not be blocked by an unavailable push endpoint.
    }
  }

  Future<void> _registerClientId(String clientId) async {
    final normalized = clientId.trim();
    if (normalized.isEmpty) return;
    _clientId = normalized;
    final snapshot = ref.read(sessionControllerProvider).asData?.value;
    if (!(snapshot?.isAuthenticated ?? false)) return;
    final config = ref.read(appConfigProvider);
    final deviceId = snapshot!.deviceId!;
    final registrationKey =
        '${snapshot.userId}|$deviceId|$normalized|${config.appVersion}|${config.environment.name}';
    if (registrationKey == _lastRegistrationKey) return;
    try {
      await ref
          .read(pushApiProvider)
          .registerToken(
            deviceId: deviceId,
            platform: defaultTargetPlatform.name,
            provider: 'getui',
            token: normalized,
            appVersion: config.appVersion,
            environment: config.environment.name,
            locale: PlatformDispatcher.instance.locale.toLanguageTag(),
          );
      _lastRegistrationKey = registrationKey;
    } on Object {
      // The CID callback can repeat; a later callback or app resume retries it.
    }
  }

  Future<void> _handleClickedEvent(Map<String, dynamic> event) async {
    final data = _notificationData(event);
    if (data != null) handleMessage(data);
  }

  Future<void> _handleForegroundEvent(Map<String, dynamic> event) async {
    final data = _notificationData(event);
    final notification = data == null ? null : PushNotification.fromData(data);
    if (notification == null) return;
    if (!_seenForegroundIds.add(notification.notificationId)) return;
    if (_seenForegroundIds.length > 64) {
      _seenForegroundIds.remove(_seenForegroundIds.first);
    }
    state = state.copyWith(foregroundNotification: notification);
  }

  Map<String, dynamic>? _notificationData(Map<String, dynamic> event) {
    for (final key in const <String>['payload', 'content']) {
      final value = event[key];
      if (value is Map) {
        return value.map((key, value) => MapEntry(key.toString(), value));
      }
      if (value is! String || value.trim().isEmpty) continue;
      try {
        final decoded = jsonDecode(value);
        if (decoded is Map) {
          return decoded.map((key, value) => MapEntry(key.toString(), value));
        }
      } on FormatException {
        continue;
      }
    }
    return null;
  }
}
