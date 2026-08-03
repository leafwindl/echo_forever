import 'package:echo_app/shared/utils/input_validators.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('InputValidators.normalizeMainlandPhone', () {
    test('normalizes supported mainland phone forms', () {
      expect(
        InputValidators.normalizeMainlandPhone('138 0013 8000'),
        '+8613800138000',
      );
      expect(
        InputValidators.normalizeMainlandPhone('0086-13800138000'),
        '+8613800138000',
      );
      expect(
        InputValidators.normalizeMainlandPhone('+8613800138000'),
        '+8613800138000',
      );
    });

    test('rejects unsupported phone numbers', () {
      expect(
        () => InputValidators.normalizeMainlandPhone('12345'),
        throwsFormatException,
      );
    });
  });
}
