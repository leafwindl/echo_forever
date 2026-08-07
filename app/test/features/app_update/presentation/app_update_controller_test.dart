import 'package:echo_app/core/storage/preferences_store.dart';
import 'package:echo_app/core/storage/storage_keys.dart';
import 'package:echo_app/features/app_update/data/app_update_api.dart';
import 'package:echo_app/features/app_update/data/direct_update_bridge.dart';
import 'package:echo_app/features/app_update/domain/app_release.dart';
import 'package:echo_app/features/app_update/presentation/app_update_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_preferences_store.dart';

void main() {
  test('automatic check is skipped within the five-minute window', () async {
    final now = DateTime.utc(2026, 8, 6, 10);
    final preferences = FakePreferencesStore(<String, Object?>{
      StorageKeys.appUpdateLastAutomaticCheck: now
          .subtract(const Duration(minutes: 2))
          .toIso8601String(),
    });
    final platform = FakeDirectUpdatePlatform();
    final container = _container(
      api: FakeAppUpdateApi(),
      platform: platform,
      preferences: preferences,
      now: now,
    );
    addTearDown(container.dispose);

    final result = await container
        .read(appUpdateControllerProvider.notifier)
        .checkForUpdate(manual: false);

    expect(result, UpdateCheckResult.skipped);
    expect(platform.appInfoCalls, 0);
  });

  test('automatic check resumes after the five-minute window', () async {
    final now = DateTime.utc(2026, 8, 6, 10);
    final preferences = FakePreferencesStore(<String, Object?>{
      StorageKeys.appUpdateLastAutomaticCheck: now
          .subtract(AppUpdateController.automaticCheckInterval)
          .toIso8601String(),
    });
    final platform = FakeDirectUpdatePlatform();
    final api = FakeAppUpdateApi();
    final container = _container(
      api: api,
      platform: platform,
      preferences: preferences,
      now: now,
    );
    addTearDown(container.dispose);

    final result = await container
        .read(appUpdateControllerProvider.notifier)
        .checkForUpdate(manual: false);

    expect(result, UpdateCheckResult.upToDate);
    expect(platform.appInfoCalls, 1);
    expect(api.latestCalls, 1);
  });

  test('manual check exposes a validated newer release', () async {
    final api = FakeAppUpdateApi(release: releaseFixture());
    final container = _container(api: api);
    addTearDown(container.dispose);

    final result = await container
        .read(appUpdateControllerProvider.notifier)
        .checkForUpdate(manual: true);

    final state = container.read(appUpdateControllerProvider);
    expect(result, UpdateCheckResult.available);
    expect(state.phase, AppUpdatePhase.available);
    expect(state.release?.versionCode, 3);
  });

  test(
    'automatic checks do not reopen a release dismissed in this session',
    () async {
      final api = FakeAppUpdateApi(release: releaseFixture());
      final container = _container(api: api);
      addTearDown(container.dispose);
      final controller = container.read(appUpdateControllerProvider.notifier);

      await controller.checkForUpdate(manual: true);
      controller.dismiss();

      final automaticResult = await controller.checkForUpdate(manual: false);
      expect(automaticResult, UpdateCheckResult.upToDate);
      expect(container.read(appUpdateControllerProvider).release, isNull);

      final manualResult = await controller.checkForUpdate(manual: true);
      expect(manualResult, UpdateCheckResult.available);
    },
  );

  test(
    'requests permission then downloads, verifies and opens installer',
    () async {
      final api = FakeAppUpdateApi(release: releaseFixture());
      final platform = FakeDirectUpdatePlatform(canInstall: false);
      final container = _container(api: api, platform: platform);
      addTearDown(container.dispose);
      final controller = container.read(appUpdateControllerProvider.notifier);
      await controller.checkForUpdate(manual: true);

      await controller.startUpdate();
      expect(
        container.read(appUpdateControllerProvider).phase,
        AppUpdatePhase.permissionRequired,
      );
      expect(platform.permissionSettingsCalls, 1);

      platform.canInstall = true;
      platform.statuses.add(
        const NativeDownloadStatus(phase: NativeDownloadPhase.ready),
      );
      await controller.startUpdate();

      expect(api.downloadCalls, 1);
      expect(platform.startCalls, 1);
      expect(platform.launchCalls, 1);
      expect(
        container.read(appUpdateControllerProvider).phase,
        AppUpdatePhase.launchingInstaller,
      );
    },
  );

  test('rejects release metadata for another package', () async {
    final api = FakeAppUpdateApi(
      release: releaseFixture(packageName: 'example.invalid'),
    );
    final container = _container(api: api);
    addTearDown(container.dispose);

    final result = await container
        .read(appUpdateControllerProvider.notifier)
        .checkForUpdate(manual: true);

    final state = container.read(appUpdateControllerProvider);
    expect(result, UpdateCheckResult.failed);
    expect(state.phase, AppUpdatePhase.failed);
    expect(state.release, isNull);
  });
}

ProviderContainer _container({
  FakeAppUpdateApi? api,
  FakeDirectUpdatePlatform? platform,
  PreferencesStore? preferences,
  DateTime? now,
}) {
  return ProviderContainer(
    overrides: [
      appUpdateApiProvider.overrideWithValue(api ?? FakeAppUpdateApi()),
      directUpdatePlatformProvider.overrideWithValue(
        platform ?? FakeDirectUpdatePlatform(),
      ),
      preferencesStoreProvider.overrideWithValue(
        preferences ?? FakePreferencesStore(),
      ),
      appUpdateClockProvider.overrideWithValue(
        () => now ?? DateTime.utc(2026, 8, 6),
      ),
    ],
  );
}

AppRelease releaseFixture({String? packageName}) {
  return AppRelease(
    releaseId: 'release-3',
    platform: 'android',
    channel: 'internal',
    packageName: packageName ?? 'cn.echoaiforever.echo_app',
    versionName: '1.0.0',
    versionCode: 3,
    minimumVersionCode: 1,
    sha256: 'a' * 64,
    sizeBytes: 1024,
    releaseNotes: const <String>['支持应用内更新'],
    mandatory: false,
  );
}

class FakeAppUpdateApi implements AppUpdateApi {
  FakeAppUpdateApi({this.release});

  AppRelease? release;
  int latestCalls = 0;
  int downloadCalls = 0;

  @override
  Future<AppRelease?> latestRelease({required int versionCode}) async {
    latestCalls += 1;
    return release;
  }

  @override
  Future<Uri> requestDownload({
    required String releaseId,
    required int versionCode,
  }) async {
    downloadCalls += 1;
    return Uri.parse('https://cos.example.test/echo.apk');
  }
}

class FakeDirectUpdatePlatform implements DirectUpdatePlatform {
  FakeDirectUpdatePlatform({this.canInstall = true});

  bool canInstall;
  int appInfoCalls = 0;
  int permissionSettingsCalls = 0;
  int startCalls = 0;
  int launchCalls = 0;
  final List<NativeDownloadStatus> statuses = <NativeDownloadStatus>[];

  @override
  Future<bool> canRequestPackageInstalls() async => canInstall;

  @override
  Future<void> cleanupUpdates(int currentVersionCode) async {}

  @override
  Future<NativeDownloadStatus> getDownloadStatus(int downloadId) async {
    return statuses.removeAt(0);
  }

  @override
  Future<InstalledAppInfo> getInstalledAppInfo() async {
    appInfoCalls += 1;
    return const InstalledAppInfo(
      packageName: 'cn.echoaiforever.echo_app',
      versionName: '1.0.0',
      versionCode: 2,
    );
  }

  @override
  Future<void> launchInstaller(int downloadId) async {
    launchCalls += 1;
  }

  @override
  Future<void> openInstallPermissionSettings() async {
    permissionSettingsCalls += 1;
  }

  @override
  Future<int> startDownload({
    required Uri url,
    required AppRelease release,
  }) async {
    startCalls += 1;
    return 12;
  }
}
