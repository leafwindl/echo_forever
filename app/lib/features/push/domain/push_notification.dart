import 'package:echo_app/core/routing/route_names.dart';

/// A validated, versioned notification intent. Only app-owned routes are accepted.
class PushNotification {
  const PushNotification({
    required this.schemaVersion,
    required this.type,
    required this.route,
    required this.notificationId,
    this.entityId,
  });

  final String schemaVersion;
  final String type;
  final String route;
  final String notificationId;
  final String? entityId;

  static PushNotification? fromData(Map<String, dynamic> data) {
    final schemaVersion = data['schema_version']?.toString();
    final type = data['type']?.toString();
    final route = data['route']?.toString();
    final notificationId = data['notification_id']?.toString();
    if (schemaVersion != '1' ||
        type == null ||
        type.isEmpty ||
        route == null ||
        route.isEmpty ||
        notificationId == null ||
        notificationId.isEmpty) {
      return null;
    }
    const allowedRoutes = <String>{'chat', 'letters', 'persona'};
    if (!allowedRoutes.contains(route)) {
      return null;
    }
    final entityId = data['entity_id']?.toString();
    return PushNotification(
      schemaVersion: schemaVersion!,
      type: type,
      route: route,
      notificationId: notificationId,
      entityId: entityId?.isEmpty == true ? null : entityId,
    );
  }

  String get appLocation => switch (route) {
    'chat' => '/chat',
    'letters' => '/letters',
    'persona' => '/persona',
    _ => '/home',
  };

  /// Keeps the entity as a non-sensitive page hint; pages still load details
  /// through their authenticated API.
  String get navigationLocation {
    if (entityId == null) return appLocation;
    return '$appLocation?entity_id=${Uri.encodeComponent(entityId!)}';
  }

  String get routeName => switch (route) {
    'chat' => RouteNames.chat,
    'letters' => RouteNames.letters,
    'persona' => RouteNames.persona,
    _ => RouteNames.home,
  };
}
