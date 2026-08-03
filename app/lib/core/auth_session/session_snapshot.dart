enum SessionAvailability { online, temporarilyOffline }

class SessionSnapshot {
  const SessionSnapshot._({
    required this.userId,
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
    required this.accessExpiresAt,
    required this.refreshExpiresAt,
    required this.deviceId,
    required this.availability,
  });

  const SessionSnapshot.signedOut()
    : userId = null,
      accessToken = null,
      refreshToken = null,
      tokenType = 'bearer',
      accessExpiresAt = null,
      refreshExpiresAt = null,
      deviceId = null,
      availability = SessionAvailability.online;

  factory SessionSnapshot.authenticated({
    required String userId,
    required String accessToken,
    required String refreshToken,
    required String tokenType,
    required DateTime accessExpiresAt,
    required DateTime refreshExpiresAt,
    required String deviceId,
  }) {
    return SessionSnapshot._(
      userId: userId,
      accessToken: accessToken,
      refreshToken: refreshToken,
      tokenType: tokenType,
      accessExpiresAt: accessExpiresAt.toUtc(),
      refreshExpiresAt: refreshExpiresAt.toUtc(),
      deviceId: deviceId,
      availability: SessionAvailability.online,
    );
  }

  factory SessionSnapshot.fromJson(Map<String, Object?> json) {
    return SessionSnapshot.authenticated(
      userId: json['user_id']! as String,
      accessToken: json['access_token']! as String,
      refreshToken: json['refresh_token']! as String,
      tokenType: json['token_type']! as String,
      accessExpiresAt: DateTime.parse(json['access_expires_at']! as String),
      refreshExpiresAt: DateTime.parse(json['refresh_expires_at']! as String),
      deviceId: json['device_id']! as String,
    );
  }

  final String? userId;
  final String? accessToken;
  final String? refreshToken;
  final String tokenType;
  final DateTime? accessExpiresAt;
  final DateTime? refreshExpiresAt;
  final String? deviceId;
  final SessionAvailability availability;

  bool get isAuthenticated =>
      userId != null &&
      accessToken != null &&
      refreshToken != null &&
      deviceId != null;

  bool needsRefresh({
    DateTime? now,
    Duration safetyWindow = const Duration(minutes: 2),
  }) {
    if (!isAuthenticated || accessExpiresAt == null) {
      return false;
    }
    return !accessExpiresAt!.isAfter(
      (now ?? DateTime.now().toUtc()).add(safetyWindow),
    );
  }

  bool get accessTokenIsUsable =>
      accessExpiresAt?.isAfter(DateTime.now().toUtc()) ?? false;

  SessionSnapshot copyWithAvailability(SessionAvailability value) {
    if (!isAuthenticated) {
      return this;
    }
    return SessionSnapshot._(
      userId: userId,
      accessToken: accessToken,
      refreshToken: refreshToken,
      tokenType: tokenType,
      accessExpiresAt: accessExpiresAt,
      refreshExpiresAt: refreshExpiresAt,
      deviceId: deviceId,
      availability: value,
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'user_id': userId,
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'token_type': tokenType,
    'access_expires_at': accessExpiresAt?.toIso8601String(),
    'refresh_expires_at': refreshExpiresAt?.toIso8601String(),
    'device_id': deviceId,
  };
}
