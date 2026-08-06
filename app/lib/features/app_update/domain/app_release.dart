class AppRelease {
  const AppRelease({
    required this.releaseId,
    required this.platform,
    required this.channel,
    required this.packageName,
    required this.versionName,
    required this.versionCode,
    required this.minimumVersionCode,
    required this.sha256,
    required this.sizeBytes,
    required this.releaseNotes,
    required this.mandatory,
  });

  factory AppRelease.fromJson(Map<String, dynamic> json) {
    final releaseNotes = json['release_notes'];
    final value = AppRelease(
      releaseId: _requiredString(json, 'release_id'),
      platform: _requiredString(json, 'platform'),
      channel: _requiredString(json, 'channel'),
      packageName: _requiredString(json, 'package_name'),
      versionName: _requiredString(json, 'version_name'),
      versionCode: _requiredPositiveInt(json, 'version_code'),
      minimumVersionCode: _requiredPositiveInt(json, 'minimum_version_code'),
      sha256: _requiredString(json, 'sha256').toLowerCase(),
      sizeBytes: _requiredPositiveInt(json, 'size_bytes'),
      releaseNotes: releaseNotes is List
          ? releaseNotes
                .map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false)
          : const <String>[],
      mandatory: json['mandatory'] == true,
    );
    if (value.platform != 'android' || value.channel != 'internal') {
      throw const FormatException('Unsupported release target');
    }
    if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(value.sha256)) {
      throw const FormatException('Invalid release SHA-256');
    }
    return value;
  }

  final String releaseId;
  final String platform;
  final String channel;
  final String packageName;
  final String versionName;
  final int versionCode;
  final int minimumVersionCode;
  final String sha256;
  final int sizeBytes;
  final List<String> releaseNotes;
  final bool mandatory;
}

class InstalledAppInfo {
  const InstalledAppInfo({
    required this.packageName,
    required this.versionName,
    required this.versionCode,
  });

  final String packageName;
  final String versionName;
  final int versionCode;
}

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key]?.toString().trim() ?? '';
  if (value.isEmpty) {
    throw FormatException('Missing $key');
  }
  return value;
}

int _requiredPositiveInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  final parsed = value is num ? value.toInt() : int.tryParse(value.toString());
  if (parsed == null || parsed <= 0) {
    throw FormatException('Invalid $key');
  }
  return parsed;
}
