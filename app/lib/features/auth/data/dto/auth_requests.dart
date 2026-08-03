class PhoneLoginRequestDto {
  const PhoneLoginRequestDto({required this.phone, required this.deviceId});

  final String phone;
  final String deviceId;

  Map<String, Object?> toJson() => <String, Object?>{
    'phone': phone,
    'device_id': deviceId,
    'purpose': 'login',
  };
}

class VerifyLoginRequestDto {
  const VerifyLoginRequestDto({
    required this.requestId,
    required this.phone,
    required this.code,
    required this.deviceId,
  });

  final String requestId;
  final String phone;
  final String code;
  final String deviceId;

  Map<String, Object?> toJson() => <String, Object?>{
    'request_id': requestId,
    'phone': phone,
    'code': code,
    'device_id': deviceId,
  };
}

class RefreshLoginRequestDto {
  const RefreshLoginRequestDto({
    required this.refreshToken,
    required this.deviceId,
  });

  final String refreshToken;
  final String deviceId;

  Map<String, Object?> toJson() => <String, Object?>{
    'refresh_token': refreshToken,
    'device_id': deviceId,
  };
}
