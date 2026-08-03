class AuthSession {
  const AuthSession({
    required this.userId,
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
    required this.accessExpiresAt,
    required this.refreshExpiresAt,
    required this.deviceId,
    this.isNewUser = false,
  });

  final String userId;
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final DateTime accessExpiresAt;
  final DateTime refreshExpiresAt;
  final String deviceId;
  final bool isNewUser;
}
