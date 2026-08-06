import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/network/endpoints.dart';
import 'package:echo_app/features/app_update/domain/app_release.dart';

class AppUpdateApi {
  const AppUpdateApi(this._client);

  final DioClient _client;

  Future<AppRelease?> latestRelease({required int versionCode}) async {
    final response = await _client.get<Map<String, dynamic>>(
      Endpoints.latestRelease,
      queryParameters: <String, dynamic>{
        'platform': 'android',
        'channel': 'internal',
        'version_code': versionCode,
      },
    );
    final body = response.data;
    if (body == null || body['update_available'] != true) {
      return null;
    }
    final release = body['release'];
    if (release is! Map) {
      throw const FormatException('Missing release metadata');
    }
    return AppRelease.fromJson(Map<String, dynamic>.from(release));
  }

  Future<Uri> requestDownload({
    required String releaseId,
    required int versionCode,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      Endpoints.releaseDownload(releaseId),
      data: <String, dynamic>{
        'platform': 'android',
        'channel': 'internal',
        'version_code': versionCode,
      },
    );
    final rawUrl = response.data?['download_url']?.toString() ?? '';
    final uri = Uri.tryParse(rawUrl);
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const FormatException('Invalid release download URL');
    }
    return uri;
  }
}
