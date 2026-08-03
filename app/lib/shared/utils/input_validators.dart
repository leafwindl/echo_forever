class InputValidators {
  const InputValidators._();

  static String? mainlandPhone(String? value) {
    if (value == null || value.trim().isEmpty) {
      return '请输入手机号';
    }
    try {
      normalizeMainlandPhone(value);
      return null;
    } on FormatException {
      return '请输入正确的中国大陆手机号';
    }
  }

  static String? verificationCode(String? value) {
    if (value == null || !RegExp(r'^\d{6}$').hasMatch(value.trim())) {
      return '请输入 6 位数字验证码';
    }
    return null;
  }

  static String normalizeMainlandPhone(String value) {
    var normalized = value.replaceAll(RegExp(r'[\s-]'), '');
    if (normalized.startsWith('0086')) {
      normalized = '+86${normalized.substring(4)}';
    } else if (RegExp(r'^1\d{10}$').hasMatch(normalized)) {
      normalized = '+86$normalized';
    }
    if (!RegExp(r'^\+861[3-9]\d{9}$').hasMatch(normalized)) {
      throw const FormatException('Unsupported mainland China phone number');
    }
    return normalized;
  }
}
