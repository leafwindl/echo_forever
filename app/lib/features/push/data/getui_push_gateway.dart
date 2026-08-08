import 'dart:io';

import 'package:getuiflut/getuiflut.dart';
import 'package:permission_handler/permission_handler.dart';

enum PushPermissionStatus { unknown, authorized, denied, unsupported }

class PushGatewayCallbacks {
  const PushGatewayCallbacks({
    required this.onClientId,
    required this.onNotificationArrived,
    required this.onNotificationClicked,
    required this.onPayload,
  });

  final Future<void> Function(String clientId) onClientId;
  final Future<void> Function(Map<String, dynamic> message)
  onNotificationArrived;
  final Future<void> Function(Map<String, dynamic> message)
  onNotificationClicked;
  final Future<void> Function(Map<String, dynamic> message) onPayload;
}

abstract interface class PushGateway {
  Future<PushPermissionStatus> initialize(PushGatewayCallbacks callbacks);

  Future<PushPermissionStatus> permissionStatus();

  Future<PushPermissionStatus> requestPermission();

  Future<String?> clientId();
}

class GetuiPushGateway implements PushGateway {
  GetuiPushGateway({Getuiflut? getui}) : _getui = getui ?? Getuiflut();

  final Getuiflut _getui;
  bool _initialized = false;

  @override
  Future<PushPermissionStatus> initialize(
    PushGatewayCallbacks callbacks,
  ) async {
    if (!Platform.isAndroid) {
      return PushPermissionStatus.unsupported;
    }
    if (!_initialized) {
      _getui.addEventHandler(
        onReceiveClientId: callbacks.onClientId,
        onNotificationMessageArrived: callbacks.onNotificationArrived,
        onNotificationMessageClicked: callbacks.onNotificationClicked,
        onReceivePayload: callbacks.onPayload,
        onTransmitUserMessageReceive: _ignoreMap,
        onReceiveOnlineState: _ignoreString,
        onRegisterDeviceToken: _ignoreString,
        onReceiveNotificationResponse: _ignoreMap,
        onAppLinkPayload: _ignoreString,
        onPushModeResult: _ignoreMap,
        onSetTagResult: _ignoreMap,
        onAliasResult: _ignoreMap,
        onQueryTagResult: _ignoreMap,
        onWillPresentNotification: _ignoreMap,
        onOpenSettingsForNotification: _ignoreMap,
        onGrantAuthorization: _ignoreString,
        onLiveActivityResult: _ignoreMap,
        onRegisterPushToStartTokenResult: _ignoreMap,
      );
      _getui.initGetuiSdk;
      _getui.onActivityCreate();
      _initialized = true;
    }
    return permissionStatus();
  }

  @override
  Future<String?> clientId() async {
    if (!_initialized || !Platform.isAndroid) return null;
    final value = (await _getui.getClientId).trim();
    return value.isEmpty ? null : value;
  }

  @override
  Future<PushPermissionStatus> permissionStatus() async {
    if (!Platform.isAndroid) return PushPermissionStatus.unsupported;
    return _mapPermission(await Permission.notification.status);
  }

  @override
  Future<PushPermissionStatus> requestPermission() async {
    if (!Platform.isAndroid) return PushPermissionStatus.unsupported;
    return _mapPermission(await Permission.notification.request());
  }

  static PushPermissionStatus _mapPermission(PermissionStatus status) {
    if (status.isGranted || status.isLimited || status.isProvisional) {
      return PushPermissionStatus.authorized;
    }
    if (status.isDenied || status.isPermanentlyDenied || status.isRestricted) {
      return PushPermissionStatus.denied;
    }
    return PushPermissionStatus.unknown;
  }

  static Future<void> _ignoreString(String _) async {}

  static Future<void> _ignoreMap(Map<String, dynamic> _) async {}
}
