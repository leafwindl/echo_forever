class PhoneLoginResponseDto {
  const PhoneLoginResponseDto({
    required this.requestId,
    required this.expiresIn,
    required this.resendAfter,
    required this.phoneMasked,
  });

  factory PhoneLoginResponseDto.fromJson(Map<String, dynamic> json) {
    return PhoneLoginResponseDto(
      requestId: json['request_id']! as String,
      expiresIn: json['expires_in']! as int,
      resendAfter: json['resend_after']! as int,
      phoneMasked: json['phone_masked']! as String,
    );
  }

  final String requestId;
  final int expiresIn;
  final int resendAfter;
  final String phoneMasked;
}

class TokenResponseDto {
  const TokenResponseDto({
    required this.userId,
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
    required this.expiresIn,
    required this.refreshExpiresIn,
    this.isNewUser = false,
  });

  factory TokenResponseDto.fromJson(Map<String, dynamic> json) {
    return TokenResponseDto(
      userId: json['user_id']! as String,
      accessToken: json['access_token']! as String,
      refreshToken: json['refresh_token']! as String,
      tokenType: json['token_type']! as String,
      expiresIn: json['expires_in']! as int,
      refreshExpiresIn: json['refresh_expires_in']! as int,
      isNewUser: json['is_new_user'] as bool? ?? false,
    );
  }

  final String userId;
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final int expiresIn;
  final int refreshExpiresIn;
  final bool isNewUser;
}
