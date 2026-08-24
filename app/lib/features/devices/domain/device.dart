class EchoDevice {
  const EchoDevice({
    required this.deviceId,
    required this.displayName,
    required this.status,
    this.clientId = '',
    this.firmwareVersion = '',
    this.lastSeenAt,
    this.wifiSsid = '',
    this.boundAt,
    this.createdAt,
    this.updatedAt,
  });

  factory EchoDevice.fromJson(Map<String, dynamic> json) {
    return EchoDevice(
      deviceId: json['device_id'] as String? ?? '',
      clientId: json['client_id'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '我的 Echo',
      firmwareVersion: json['firmware_version'] as String? ?? '',
      status: json['status'] as String? ?? 'offline',
      lastSeenAt: json['last_seen_at'] as String?,
      wifiSsid: json['wifi_ssid'] as String? ?? '',
      boundAt: json['bound_at'] as String?,
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
    );
  }

  final String deviceId;
  final String clientId;
  final String displayName;
  final String firmwareVersion;
  final String status;
  final String? lastSeenAt;
  final String wifiSsid;
  final String? boundAt;
  final String? createdAt;
  final String? updatedAt;

  bool get isOnline => status == 'online';
  String get statusLabel => switch (status) {
        'online' => '在线',
        'unclaimed' => '待绑定',
        'revoked' => '已撤销',
        _ => '离线',
      };
}

class DevicePairingClaim {
  const DevicePairingClaim({
    required this.deviceId,
    required this.clientId,
    required this.credential,
  });

  factory DevicePairingClaim.fromJson(Map<String, dynamic> json) {
    return DevicePairingClaim(
      deviceId: json['device_id'] as String? ?? '',
      clientId: json['client_id'] as String? ?? '',
      credential: json['credential'] as String? ?? '',
    );
  }

  final String deviceId;
  final String clientId;
  final String credential;
}

class SpeakerProfile {
  const SpeakerProfile({
    required this.speakerProfileId,
    required this.displayName,
    required this.role,
    required this.status,
    required this.modelName,
    required this.modelVersion,
    this.createdAt,
    this.updatedAt,
  });

  factory SpeakerProfile.fromJson(Map<String, dynamic> json) {
    return SpeakerProfile(
      speakerProfileId: json['speaker_profile_id'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '主人',
      role: json['role'] as String? ?? 'owner',
      status: json['status'] as String? ?? 'active',
      modelName: json['model_name'] as String? ?? '',
      modelVersion: json['model_version'] as String? ?? '',
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
    );
  }

  final String speakerProfileId;
  final String displayName;
  final String role;
  final String status;
  final String modelName;
  final String modelVersion;
  final String? createdAt;
  final String? updatedAt;
}
