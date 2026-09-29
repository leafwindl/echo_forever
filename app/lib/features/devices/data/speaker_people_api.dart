import 'package:dio/dio.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class SpeakerPerson {
  const SpeakerPerson(
    this.id,
    this.name,
    this.status,
    this.sampleCount, {
    this.hardwareCalibrated = false,
  });
  factory SpeakerPerson.fromJson(Map<String, dynamic> json) => SpeakerPerson(
    json['person_id'] as String,
    json['display_name'] as String,
    json['status'] as String,
    json['sample_count'] as int,
    hardwareCalibrated: json['hardware_calibrated'] == true,
  );
  final String id;
  final String name;
  final String status;
  final int sampleCount;
  final bool hardwareCalibrated;
  bool get active => status == 'active';
}

class SpeakerPeopleApi {
  const SpeakerPeopleApi(this.client);
  final DioClient client;
  String path(String deviceId) => '${Endpoints.device(deviceId)}/speakers';
  Future<Map<String, dynamic>?> pending(String deviceId) async {
    final response = await client.get<Map<String, dynamic>>(
      '${Endpoints.device(deviceId)}/speaker-enrollment-request',
    );
    final request = response.data?['request'];
    return request is Map ? Map<String, dynamic>.from(request) : null;
  }

  Future<void> approve(String deviceId, String sessionId, bool approved) async {
    await client.post<void>(
      '${Endpoints.device(deviceId)}/speaker-enrollment-request',
      data: {'session_id': sessionId, 'approved': approved},
    );
  }

  Future<Map<String, dynamic>?> calibration(String deviceId) async {
    final response = await client.get<Map<String, dynamic>>(
      '${Endpoints.device(deviceId)}/speaker-calibration',
    );
    final session = response.data?['session'];
    return session is Map ? Map<String, dynamic>.from(session) : null;
  }

  Future<Map<String, dynamic>> startCalibration(
    String deviceId,
    String personId,
  ) async {
    final response = await client.post<Map<String, dynamic>>(
      '${path(deviceId)}/$personId/calibration',
      data: {'consent': true},
    );
    return response.data!;
  }

  Future<void> cancelCalibration(String deviceId) async {
    await client.delete<void>(
      '${Endpoints.device(deviceId)}/speaker-calibration',
    );
  }

  Future<void> removeCalibration(String deviceId, String personId) async {
    await client.delete<void>('${path(deviceId)}/$personId/calibration');
  }

  Future<List<SpeakerPerson>> list(String deviceId) async {
    final response = await client.get<Map<String, dynamic>>(path(deviceId));
    return (response.data!['items'] as List)
        .map(
          (item) =>
              SpeakerPerson.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  }

  Future<SpeakerPerson> create(String deviceId, String name) async {
    final response = await client.post<Map<String, dynamic>>(
      path(deviceId),
      data: {'display_name': name.trim(), 'consent': true},
    );
    return SpeakerPerson.fromJson(response.data!);
  }

  Future<SpeakerPerson> sample(
    String deviceId,
    String personId,
    List<int> audio,
  ) async {
    final response = await client.post<Map<String, dynamic>>(
      '${path(deviceId)}/$personId/samples',
      data: FormData.fromMap({
        'audio': MultipartFile.fromBytes(
          audio,
          filename: 'sample.pcm',
          contentType: DioMediaType('audio', 'L16'),
        ),
      }),
    );
    return SpeakerPerson.fromJson(response.data!);
  }

  Future<void> delete(String deviceId, String personId) async {
    await client.delete<void>('${path(deviceId)}/$personId');
  }
}

final speakerPeopleApiProvider = Provider(
  (ref) => SpeakerPeopleApi(ref.watch(authenticatedDioClientProvider)),
);
