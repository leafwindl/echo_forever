class Redaction {
  const Redaction._();

  static const sensitiveHeaders = <String>{
    'authorization',
    'cookie',
    'set-cookie',
  };

  static String phone(String value) {
    final digits = value.replaceAll(RegExp(r'\D'), '');
    if (digits.length < 7) {
      return '***';
    }
    return '${digits.substring(0, 3)}****${digits.substring(digits.length - 4)}';
  }
}
