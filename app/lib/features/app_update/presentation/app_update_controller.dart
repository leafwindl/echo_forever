import 'dart:async';

import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/errors/error_message_mapper.dart';
import 'package:echo_app/core/observability/app_logger.dart';
import 'package:echo_app/core/storage/preferences_store.dart';
import 'package:echo_app/core/storage/storage_keys.dart';
import 'package:echo_app/features/app_update/data/app_update_api.dart';
import 'package:echo_app/features/app_update/data/direct_update_bridge.dart';
import 'package:echo_app/features/app_update/domain/app_release.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AppUpdatePhase {
  idle,
  checking,
  available,
  permissionRequired,
  downloading,
  verifying,
  readyToInstall,
  launchingInstaller,
  failed,
}

enum UpdateCheckResult { skipped, available, upToDate, failed }

class AppUpdateState {
  const AppUpdateState({
    this.phase = AppUpdatePhase.idle,
    this.release,
    this.appInfo,
    this.progress,
    this.downloadId,
    this.errorMessage,
  });

  final AppUpdatePhase phase;
  final AppRelease? release;
  final InstalledAppInfo? appInfo;
  final double? progress;
  final int? downloadId;
  final String? errorMessage;

  bool get isBusy => switch (phase) {
    AppUpdatePhase.checking ||
    AppUpdatePhase.downloading ||
    AppUpdatePhase.verifying => true,
    _ => false,
  };

  bool get showsUpdatePanel =>
      release != null &&
      phase != AppUpdatePhase.idle &&
      phase != AppUpdatePhase.checking;
}

final appUpdateApiProvider = Provider<AppUpdateApi>((ref) {
  return AppUpdateApi(ref.watch(publicDioClientProvider));
});

final directUpdatePlatformProvider = Provider<DirectUpdatePlatform>((ref) {
  return const MethodChannelDirectUpdatePlatform();
});

final appUpdateClockProvider = Provider<DateTime Function()>((ref) {
  return DateTime.now;
});

final appUpdateControllerProvider =
    NotifierProvider<AppUpdateController, AppUpdateState>(
      AppUpdateController.new,
    );

class AppUpdateController extends Notifier<AppUpdateState> {
  static const automaticCheckInterval = Duration(minutes: 5);
  static const _downloadPollInterval = Duration(milliseconds: 750);
  static const _maximumDownloadPolls = 2400;
  static const _expectedPackageName = 'cn.echoaiforever.echo_app';

  final AppLogger _logger = AppLogger('AppUpdate');
  bool _initialized = false;
  bool _disposed = false;
  int _operationId = 0;
  int? _dismissedReleaseVersionCode;

  @override
  AppUpdateState build() {
    ref.onDispose(() {
      _disposed = true;
      _operationId += 1;
    });
    return const AppUpdateState();
  }

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    await checkForUpdate(manual: false);
  }

  Future<UpdateCheckResult> checkForUpdate({required bool manual}) async {
    if (state.isBusy || (!manual && state.release != null)) {
      return UpdateCheckResult.skipped;
    }
    final preferences = ref.read(preferencesStoreProvider);
    final now = ref.read(appUpdateClockProvider)();
    if (!manual && await _checkedRecently(preferences, now)) {
      return UpdateCheckResult.skipped;
    }

    state = const AppUpdateState(phase: AppUpdatePhase.checking);
    if (!manual) {
      await preferences.setString(
        StorageKeys.appUpdateLastAutomaticCheck,
        now.toUtc().toIso8601String(),
      );
    }

    try {
      final platform = ref.read(directUpdatePlatformProvider);
      final appInfo = await platform.getInstalledAppInfo();
      _validateInstalledApp(appInfo);
      await platform.cleanupUpdates(appInfo.versionCode);
      final release = await ref
          .read(appUpdateApiProvider)
          .latestRelease(versionCode: appInfo.versionCode);
      if (release == null) {
        state = const AppUpdateState();
        return UpdateCheckResult.upToDate;
      }
      _validateRelease(release, appInfo);
      if (!manual && _dismissedReleaseVersionCode == release.versionCode) {
        state = const AppUpdateState();
        return UpdateCheckResult.upToDate;
      }
      _dismissedReleaseVersionCode = null;
      state = AppUpdateState(
        phase: AppUpdatePhase.available,
        release: release,
        appInfo: appInfo,
      );
      return UpdateCheckResult.available;
    } on Object catch (error, stackTrace) {
      _logger.warning('Update check failed', error, stackTrace);
      state = manual
          ? AppUpdateState(
              phase: AppUpdatePhase.failed,
              errorMessage: _errorMessage(error),
            )
          : const AppUpdateState();
      return UpdateCheckResult.failed;
    }
  }

  Future<void> startUpdate() async {
    final release = state.release;
    final appInfo = state.appInfo;
    if (release == null || appInfo == null || state.isBusy) return;
    final platform = ref.read(directUpdatePlatformProvider);
    try {
      if (!await platform.canRequestPackageInstalls()) {
        state = AppUpdateState(
          phase: AppUpdatePhase.permissionRequired,
          release: release,
          appInfo: appInfo,
        );
        await platform.openInstallPermissionSettings();
        return;
      }

      final operationId = ++_operationId;
      state = AppUpdateState(
        phase: AppUpdatePhase.downloading,
        release: release,
        appInfo: appInfo,
        progress: 0,
      );
      final url = await ref
          .read(appUpdateApiProvider)
          .requestDownload(
            releaseId: release.releaseId,
            versionCode: appInfo.versionCode,
          );
      final downloadId = await platform.startDownload(
        url: url,
        release: release,
      );
      state = AppUpdateState(
        phase: AppUpdatePhase.downloading,
        release: release,
        appInfo: appInfo,
        progress: 0,
        downloadId: downloadId,
      );
      await _pollDownload(operationId, downloadId, release, appInfo);
    } on Object catch (error, stackTrace) {
      _logger.warning('Update download failed', error, stackTrace);
      _fail(error, release: release, appInfo: appInfo);
    }
  }

  Future<void> launchInstaller() async {
    final release = state.release;
    final appInfo = state.appInfo;
    final downloadId = state.downloadId;
    if (release == null || appInfo == null || downloadId == null) return;
    try {
      state = AppUpdateState(
        phase: AppUpdatePhase.launchingInstaller,
        release: release,
        appInfo: appInfo,
        progress: 1,
        downloadId: downloadId,
      );
      await ref.read(directUpdatePlatformProvider).launchInstaller(downloadId);
    } on Object catch (error, stackTrace) {
      _logger.warning('Installer launch failed', error, stackTrace);
      _fail(error, release: release, appInfo: appInfo, downloadId: downloadId);
    }
  }

  void dismiss() {
    if (state.release?.mandatory == true || state.isBusy) return;
    _dismissedReleaseVersionCode = state.release?.versionCode;
    _operationId += 1;
    state = const AppUpdateState();
  }

  void clearFailure() {
    if (state.phase == AppUpdatePhase.failed && state.release == null) {
      state = const AppUpdateState();
    }
  }

  Future<void> _pollDownload(
    int operationId,
    int downloadId,
    AppRelease release,
    InstalledAppInfo appInfo,
  ) async {
    final platform = ref.read(directUpdatePlatformProvider);
    for (var attempt = 0; attempt < _maximumDownloadPolls; attempt += 1) {
      if (_disposed || operationId != _operationId) return;
      final status = await platform.getDownloadStatus(downloadId);
      if (_disposed || operationId != _operationId) return;
      switch (status.phase) {
        case NativeDownloadPhase.pending:
        case NativeDownloadPhase.downloading:
          state = AppUpdateState(
            phase: AppUpdatePhase.downloading,
            release: release,
            appInfo: appInfo,
            progress: status.progress,
            downloadId: downloadId,
          );
        case NativeDownloadPhase.verifying:
          state = AppUpdateState(
            phase: AppUpdatePhase.verifying,
            release: release,
            appInfo: appInfo,
            progress: 1,
            downloadId: downloadId,
          );
        case NativeDownloadPhase.ready:
          state = AppUpdateState(
            phase: AppUpdatePhase.readyToInstall,
            release: release,
            appInfo: appInfo,
            progress: 1,
            downloadId: downloadId,
          );
          await launchInstaller();
          return;
        case NativeDownloadPhase.failed:
          throw PlatformException(
            code: status.errorCode ?? 'DOWNLOAD_FAILED',
            message: status.error ?? 'APK download failed',
          );
      }
      await Future<void>.delayed(_downloadPollInterval);
    }
    throw TimeoutException('APK download timed out');
  }

  Future<bool> _checkedRecently(
    PreferencesStore preferences,
    DateTime now,
  ) async {
    final raw = await preferences.getString(
      StorageKeys.appUpdateLastAutomaticCheck,
    );
    final previous = DateTime.tryParse(raw ?? '');
    if (previous == null) return false;
    return now.toUtc().isBefore(previous.toUtc().add(automaticCheckInterval));
  }

  void _validateInstalledApp(InstalledAppInfo appInfo) {
    if (appInfo.packageName != _expectedPackageName ||
        appInfo.versionCode <= 0) {
      throw const FormatException('Installed app identity is invalid');
    }
  }

  void _validateRelease(AppRelease release, InstalledAppInfo appInfo) {
    if (release.packageName != appInfo.packageName ||
        release.versionCode <= appInfo.versionCode) {
      throw const FormatException('Release does not upgrade this app');
    }
  }

  void _fail(
    Object error, {
    required AppRelease release,
    required InstalledAppInfo appInfo,
    int? downloadId,
  }) {
    state = AppUpdateState(
      phase: AppUpdatePhase.failed,
      release: release,
      appInfo: appInfo,
      downloadId: downloadId,
      errorMessage: _errorMessage(error),
    );
  }

  String _errorMessage(Object error) {
    if (error is AppException) {
      return ErrorMessageMapper.toChinese(error);
    }
    if (error is FormatException) {
      return '更新信息校验失败，请稍后重试';
    }
    if (error is PlatformException) {
      return switch (error.code) {
        'APK_HASH_MISMATCH' => '安装包校验失败，请重新下载',
        'APK_SIZE_MISMATCH' => '安装包下载不完整，请重新下载',
        'APK_SIGNATURE_MISMATCH' => '安装包签名不一致，已停止安装',
        'APK_PACKAGE_MISMATCH' => '安装包不是 Echo，已停止安装',
        'APK_VERSION_INVALID' => '安装包版本无效，已停止安装',
        _ => '无法启动系统安装程序，请稍后重试',
      };
    }
    return '更新失败，请检查网络后重试';
  }
}
