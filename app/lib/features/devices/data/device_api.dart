import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';
import 'package:echo_app/features/devices/domain/device.dart';

class DeviceApi {
  const DeviceApi(this._client);

  final DioClient _client;

  Future<List<EchoDevice>> listDevices() async {
    final response = await _client.get<Map<String, dynamic>>(Endpoints.devices);
    final items = response.data?['items'];
    if (items is! List) return const [];
    return items
        .whereType<Map>()
        .map((item) => EchoDevice.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<DevicePairingClaim> claimPairing({
    required String pairingId,
    required String code,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      Endpoints.devicePairingClaim,
      data: <String, Object?>{'pairing_id': pairingId, 'code': code},
    );
    return DevicePairingClaim.fromJson(response.data!);
  }

  Future<EchoDevice> updateDevice(String deviceId, String displayName) async {
    final response = await _client.patch<Map<String, dynamic>>(
      Endpoints.device(deviceId),
      data: <String, Object?>{'display_name': displayName},
    );
    return EchoDevice.fromJson(response.data!);
  }

  Future<void> unbindDevice(String deviceId) => _client.delete<void>(Endpoints.device(deviceId));

  Future<DevicePairingClaim> rotateCredential(String deviceId) async {
    final response = await _client.post<Map<String, dynamic>>(
      Endpoints.deviceCredentialRotate(deviceId),
    );
    return DevicePairingClaim.fromJson(response.data!);
  }

  Future<SpeakerProfile?> getSpeaker(String deviceId) async {
    final response = await _client.get<Map<String, dynamic>?>(Endpoints.deviceSpeaker(deviceId));
    final data = response.data;
    return data == null ? null : SpeakerProfile.fromJson(data);
  }

  Future<void> deleteSpeaker(String deviceId) => _client.delete<void>(Endpoints.deviceSpeaker(deviceId));

  Future<void> enrollSpeaker(String deviceId, List<int> pcm16Audio) async {
    final form = FormData.fromMap(<String, dynamic>{
      'audio': MultipartFile.fromBytes(
        pcm16Audio,
        filename: 'voice.pcm',
        contentType: DioMediaType('audio', 'L16'),
      ),
    });
    await _client.post<Map<String, dynamic>>(
      Endpoints.deviceSpeakerEnrollment(deviceId),
      data: form,
    );
  }
}
