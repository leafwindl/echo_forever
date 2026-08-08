import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';
import 'package:echo_app/features/proactive_chat/domain/proactive_chat.dart';

class ProactiveChatApi {
  const ProactiveChatApi(this._client);

  final DioClient _client;

  Future<ProactiveChatPreferences> getPreferences() async {
    final response = await _client.get<Map<String, dynamic>>(
      Endpoints.proactivePreferences,
    );
    return ProactiveChatPreferences.fromJson(response.data!);
  }

  Future<ProactiveChatPreferences> savePreferences(
    ProactiveChatPreferences preferences,
  ) async {
    final response = await _client.put<Map<String, dynamic>>(
      Endpoints.proactivePreferences,
      data: preferences.toJson(),
    );
    return ProactiveChatPreferences.fromJson(response.data!);
  }

  Future<List<ChatSchedule>> listSchedules() async {
    final response = await _client.get<Map<String, dynamic>>(
      Endpoints.proactiveSchedules,
    );
    final values = response.data?['items'] as List? ?? const <Object?>[];
    return values
        .whereType<Map<String, dynamic>>()
        .map(ChatSchedule.fromJson)
        .toList(growable: false);
  }

  Future<ChatSchedule> updateSchedule(String scheduleId, String status) async {
    final response = await _client.put<Map<String, dynamic>>(
      Endpoints.proactiveSchedule(scheduleId),
      data: <String, dynamic>{'status': status},
    );
    return ChatSchedule.fromJson(response.data!);
  }

  Future<void> deleteSchedule(String scheduleId) {
    return _client.delete<void>(Endpoints.proactiveSchedule(scheduleId));
  }
}
