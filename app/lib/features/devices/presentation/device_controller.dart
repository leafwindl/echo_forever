import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/devices/data/device_api.dart';
import 'package:echo_app/features/devices/data/device_repository.dart';
import 'package:echo_app/features/devices/domain/device.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class DeviceState {
  const DeviceState({
    required this.devices,
    this.isBusy = false,
    this.error,
    this.speakers = const <String, SpeakerProfile?>{},
  });

  final List<EchoDevice> devices;
  final bool isBusy;
  final AppException? error;
  final Map<String, SpeakerProfile?> speakers;

  DeviceState copyWith({
    List<EchoDevice>? devices,
    bool? isBusy,
    AppException? error,
    bool clearError = false,
    Map<String, SpeakerProfile?>? speakers,
  }) {
    return DeviceState(
      devices: devices ?? this.devices,
      isBusy: isBusy ?? this.isBusy,
      error: clearError ? null : error ?? this.error,
      speakers: speakers ?? this.speakers,
    );
  }
}

class DeviceController extends AsyncNotifier<DeviceState> {
  @override
  Future<DeviceState> build() async {
    try {
      final devices = await ref.read(deviceRepositoryProvider).listDevices();
      return DeviceState(devices: devices);
    } on Object catch (error) {
      return DeviceState(devices: const [], error: _asException(error));
    }
  }

  Future<void> refresh() async {
    final current = state.asData?.value ?? const DeviceState(devices: []);
    state = AsyncData(current.copyWith(isBusy: true, clearError: true));
    try {
      final devices = await ref.read(deviceRepositoryProvider).listDevices();
      state = AsyncData(
        current.copyWith(devices: devices, isBusy: false, clearError: true),
      );
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isBusy: false, error: _asException(error)),
      );
    }
  }

  Future<bool> waitUntilOnline(String deviceId) async {
    final repository = ref.read(deviceRepositoryProvider);
    for (var attempt = 0; attempt < 20; attempt++) {
      final devices = await repository.listDevices();
      EchoDevice? device;
      for (final item in devices) {
        if (item.deviceId == deviceId) {
          device = item;
          break;
        }
      }
      if (device?.isOnline == true) {
        state = AsyncData(
          (state.asData?.value ?? const DeviceState(devices: [])).copyWith(
            devices: devices,
            clearError: true,
          ),
        );
        return true;
      }
      if (attempt < 19) {
        await Future<void>.delayed(const Duration(seconds: 1));
      }
    }
    await refresh();
    return false;
  }

  Future<bool> connectDevice(String deviceId) async {
    try {
      await ref.read(deviceRepositoryProvider).connectDevice(deviceId);
      state = AsyncData(
        (state.asData?.value ?? const DeviceState(devices: [])).copyWith(clearError: true),
      );
      return true;
    } on Object catch (error) {
      state = AsyncData(
        (state.asData?.value ?? const DeviceState(devices: [])).copyWith(
          error: _asException(error),
        ),
      );
      rethrow;
    }
  }

  Future<bool> claimPairing({
    required String pairingId,
    required String code,
  }) async {
    final current = state.asData?.value ?? const DeviceState(devices: []);
    state = AsyncData(current.copyWith(isBusy: true, clearError: true));
    try {
      await ref
          .read(deviceRepositoryProvider)
          .claimPairing(pairingId: pairingId, code: code);
      await refresh();
      return true;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isBusy: false, error: _asException(error)),
      );
      return false;
    }
  }

  Future<bool> rename(EchoDevice device, String name) async {
    final current = state.asData?.value ?? const DeviceState(devices: []);
    state = AsyncData(current.copyWith(isBusy: true, clearError: true));
    try {
      final updated = await ref
          .read(deviceRepositoryProvider)
          .updateDevice(device.deviceId, name);
      final devices = current.devices
          .map((item) => item.deviceId == updated.deviceId ? updated : item)
          .toList();
      state = AsyncData(
        current.copyWith(devices: devices, isBusy: false, clearError: true),
      );
      return true;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isBusy: false, error: _asException(error)),
      );
      return false;
    }
  }

  Future<bool> unbind(EchoDevice device) async {
    final current = state.asData?.value ?? const DeviceState(devices: []);
    state = AsyncData(current.copyWith(isBusy: true, clearError: true));
    try {
      await ref.read(deviceRepositoryProvider).unbindDevice(device.deviceId);
      state = AsyncData(
        current.copyWith(
          devices: current.devices
              .where((item) => item.deviceId != device.deviceId)
              .toList(),
          isBusy: false,
          clearError: true,
        ),
      );
      return true;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isBusy: false, error: _asException(error)),
      );
      return false;
    }
  }

  Future<SpeakerProfile?> loadSpeaker(EchoDevice device) async {
    try {
      final profile = await ref
          .read(deviceRepositoryProvider)
          .getSpeaker(device.deviceId);
      final current = state.asData?.value ?? const DeviceState(devices: []);
      state = AsyncData(
        current.copyWith(
          speakers: <String, SpeakerProfile?>{
            ...current.speakers,
            device.deviceId: profile,
          },
        ),
      );
      return profile;
    } on Object catch (error) {
      state = AsyncData(
        (state.asData?.value ?? const DeviceState(devices: [])).copyWith(
          error: _asException(error),
        ),
      );
      return null;
    }
  }

  Future<SpeakerEnrollment?> enrollSpeaker(
    EchoDevice device,
    List<int> pcm16Audio,
  ) async {
    try {
      final result = await ref
          .read(deviceRepositoryProvider)
          .enrollSpeaker(device.deviceId, pcm16Audio);
      await loadSpeaker(device);
      return result;
    } on Object catch (error) {
      state = AsyncData(
        (state.asData?.value ?? const DeviceState(devices: [])).copyWith(
          error: _asException(error),
        ),
      );
      return null;
    }
  }

  Future<bool> deleteSpeaker(EchoDevice device) async {
    try {
      await ref.read(deviceRepositoryProvider).deleteSpeaker(device.deviceId);
      final current = state.asData?.value ?? const DeviceState(devices: []);
      state = AsyncData(
        current.copyWith(
          speakers: <String, SpeakerProfile?>{
            ...current.speakers,
            device.deviceId: null,
          },
          clearError: true,
        ),
      );
      return true;
    } on Object catch (error) {
      state = AsyncData(
        (state.asData?.value ?? const DeviceState(devices: [])).copyWith(
          error: _asException(error),
        ),
      );
      return false;
    }
  }

  AppException _asException(Object error) => error is AppException
      ? error
      : const AppException(kind: AppExceptionKind.unexpected);
}

final deviceApiProvider = Provider<DeviceApi>(
  (ref) => DeviceApi(ref.watch(authenticatedDioClientProvider)),
);
final deviceRepositoryProvider = Provider<DeviceRepository>(
  (ref) => DeviceRepositoryImpl(ref.watch(deviceApiProvider)),
);
final deviceControllerProvider =
    AsyncNotifierProvider<DeviceController, DeviceState>(DeviceController.new);
