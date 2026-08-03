import 'package:flutter_riverpod/flutter_riverpod.dart';

class PendingRouteStore extends Notifier<String?> {
  @override
  String? build() => null;

  void clear() => state = null;

  void remember(String location) => state = location;

  String? take() {
    final route = state;
    state = null;
    return route;
  }
}

final pendingRouteStoreProvider = NotifierProvider<PendingRouteStore, String?>(
  PendingRouteStore.new,
);
