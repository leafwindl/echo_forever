import 'package:echo_app/features/presence/data/presence_api.dart';
import 'package:echo_app/features/presence/domain/presence.dart';

abstract interface class PresenceRepository {
  Future<PresenceSnapshot> getPresence();
}

class PresenceRepositoryImpl implements PresenceRepository {
  const PresenceRepositoryImpl(this._api);

  final PresenceApi _api;

  @override
  Future<PresenceSnapshot> getPresence() => _api.getPresence();
}
