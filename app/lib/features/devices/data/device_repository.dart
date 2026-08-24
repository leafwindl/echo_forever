import 'package:echo_app/features/devices/data/device_api.dart';
import 'package:echo_app/features/devices/domain/device.dart';

abstract interface class DeviceRepository {
  Future<List<EchoDevice>> listDevices();
  Future<DevicePairingClaim> claimPairing({required String pairingId, required String code});
  Future<EchoDevice> updateDevice(String deviceId, String displayName);
  Future<void> unbindDevice(String deviceId);
  Future<DevicePairingClaim> rotateCredential(String deviceId);
  Future<SpeakerProfile?> getSpeaker(String deviceId);
  Future<void> deleteSpeaker(String deviceId);
}

class DeviceRepositoryImpl implements DeviceRepository {
  const DeviceRepositoryImpl(this._api);

  final DeviceApi _api;

  @override
  Future<List<EchoDevice>> listDevices() => _api.listDevices();

  @override
  Future<DevicePairingClaim> claimPairing({required String pairingId, required String code}) =>
      _api.claimPairing(pairingId: pairingId, code: code);

  @override
  Future<EchoDevice> updateDevice(String deviceId, String displayName) =>
      _api.updateDevice(deviceId, displayName);

  @override
  Future<void> unbindDevice(String deviceId) => _api.unbindDevice(deviceId);

  @override
  Future<DevicePairingClaim> rotateCredential(String deviceId) => _api.rotateCredential(deviceId);

  @override
  Future<SpeakerProfile?> getSpeaker(String deviceId) => _api.getSpeaker(deviceId);

  @override
  Future<void> deleteSpeaker(String deviceId) => _api.deleteSpeaker(deviceId);
}
