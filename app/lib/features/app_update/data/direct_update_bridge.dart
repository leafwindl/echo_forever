import 'package:echo_app/features/app_update/domain/app_release.dart';
import 'package:flutter/services.dart';

enum NativeDownloadPhase { pending, downloading, verifying, ready, failed }

class NativeDownloadStatus {
  const NativeDownloadStatus({
    required this.phase,
    this.downloadedBytes = 0,
    this.totalBytes = 0,
    this.errorCode,
    this.error,
  });

  final NativeDownloadPhase phase;
  final int downloadedBytes;
  final int totalBytes;
  final String? errorCode;
  final String? error;

  double? get progress => totalBytes > 0
      ? (downloadedBytes / totalBytes).clamp(0, 1).toDouble()
      : null;
}

abstract interface class DirectUpdatePlatform {
  Future<InstalledAppInfo> getInstalledAppInfo();
  Future<bool> canRequestPackageInstalls();
  Future<void> openInstallPermissionSettings();
  Future<void> cleanupUpdates(int currentVersionCode);
  Future<int> startDownload({required Uri url, required AppRelease release});
  Future<NativeDownloadStatus> getDownloadStatus(int downloadId);
  Future<void> launchInstaller(int downloadId);
}

class MethodChannelDirectUpdatePlatform implements DirectUpdatePlatform {
  const MethodChannelDirectUpdatePlatform();

  static const _channel = MethodChannel(
    'cn.echoaiforever.echo_app/direct_update',
  );

  @override
  Future<InstalledAppInfo> getInstalledAppInfo() async {
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'getAppInfo',
    );
    if (result == null) {
      throw PlatformException(code: 'APP_INFO_UNAVAILABLE');
    }
    return InstalledAppInfo(
      packageName: result['packageName']?.toString() ?? '',
      versionName: result['versionName']?.toString() ?? '',
      versionCode: _intValue(result['versionCode']),
    );
  }

  @override
  Future<bool> canRequestPackageInstalls() async {
    return await _channel.invokeMethod<bool>('canRequestPackageInstalls') ??
        false;
  }

  @override
  Future<void> openInstallPermissionSettings() =>
      _channel.invokeMethod<void>('openInstallPermissionSettings');

  @override
  Future<void> cleanupUpdates(int currentVersionCode) =>
      _channel.invokeMethod<void>('cleanupUpdates', <String, dynamic>{
        'currentVersionCode': currentVersionCode,
      });

  @override
  Future<int> startDownload({
    required Uri url,
    required AppRelease release,
  }) async {
    final id = await _channel
        .invokeMethod<num>('startDownload', <String, dynamic>{
          'url': url.toString(),
          'sha256': release.sha256,
          'sizeBytes': release.sizeBytes,
          'packageName': release.packageName,
          'versionCode': release.versionCode,
        });
    if (id == null || id.toInt() <= 0) {
      throw PlatformException(code: 'DOWNLOAD_NOT_STARTED');
    }
    return id.toInt();
  }

  @override
  Future<NativeDownloadStatus> getDownloadStatus(int downloadId) async {
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'getDownloadStatus',
      <String, dynamic>{'downloadId': downloadId},
    );
    if (result == null) {
      throw PlatformException(code: 'DOWNLOAD_STATUS_UNAVAILABLE');
    }
    final phase = switch (result['status']?.toString()) {
      'pending' => NativeDownloadPhase.pending,
      'downloading' => NativeDownloadPhase.downloading,
      'verifying' => NativeDownloadPhase.verifying,
      'ready' => NativeDownloadPhase.ready,
      _ => NativeDownloadPhase.failed,
    };
    return NativeDownloadStatus(
      phase: phase,
      downloadedBytes: _intValue(result['downloadedBytes']),
      totalBytes: _intValue(result['totalBytes']),
      errorCode: result['errorCode']?.toString(),
      error: result['error']?.toString(),
    );
  }

  @override
  Future<void> launchInstaller(int downloadId) => _channel.invokeMethod<void>(
    'launchInstaller',
    <String, dynamic>{'downloadId': downloadId},
  );
}

int _intValue(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
