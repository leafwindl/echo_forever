class PhoneVerification {
  const PhoneVerification({
    required this.requestId,
    required this.phone,
    required this.phoneMasked,
    required this.expiresAt,
    required this.resendAt,
  });

  final String requestId;
  final String phone;
  final String phoneMasked;
  final DateTime expiresAt;
  final DateTime resendAt;
}
