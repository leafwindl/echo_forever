import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/presence/domain/presence.dart';

class PresenceApi {
  const PresenceApi(this._client);

  final DioClient _client;

  static const path = '/presence/me';

  Future<PresenceSnapshot> getPresence({int thoughtLimit = 20}) async {
    final response = await _client.get<Map<String, dynamic>>(
      path,
      queryParameters: <String, dynamic>{'thought_limit': thoughtLimit},
    );
    return PresenceSnapshot.fromJson(response.data!);
  }
}
