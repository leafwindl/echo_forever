class ErrorCode {
  const ErrorCode._();

  static const refreshInvalid = 'AUTH_REFRESH_INVALID';
  static const refreshExpired = 'AUTH_REFRESH_EXPIRED';
  static const refreshReused = 'AUTH_REFRESH_REUSED';
  static const userDisabled = 'AUTH_USER_DISABLED';
  static const codeInvalid = 'AUTH_CODE_INVALID';
  static const codeExpired = 'AUTH_CODE_EXPIRED';
  static const challengeInvalid = 'AUTH_CHALLENGE_INVALID';
  static const attemptsExceeded = 'AUTH_CODE_ATTEMPTS_EXCEEDED';
}
