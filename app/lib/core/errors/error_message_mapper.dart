import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/errors/error_code.dart';

class ErrorMessageMapper {
  const ErrorMessageMapper._();

  static String toChinese(AppException exception) {
    final codeMessage = switch (exception.serverCode) {
      ErrorCode.codeInvalid => '验证码错误，请重新输入',
      ErrorCode.codeExpired => '验证码已过期，请重新获取',
      ErrorCode.challengeInvalid => '本次验证已失效，请重新获取验证码',
      ErrorCode.attemptsExceeded => '错误次数过多，请重新获取验证码',
      'AUTH_PHONE_INVALID' => '请输入正确的中国大陆手机号',
      'AUTH_SMS_RATE_LIMITED' => '验证码发送过于频繁，请稍后再试',
      'AUTH_VERIFY_RATE_LIMITED' => '验证过于频繁，请稍后再试',
      'AUTH_SMS_PROVIDER_UNAVAILABLE' => '短信服务暂不可用，请稍后重试',
      'AUTH_SERVICE_UNAVAILABLE' => '认证服务暂不可用，请稍后重试',
      ErrorCode.userDisabled => '账号当前不可用，请联系支持',
      _ => null,
    };
    if (codeMessage != null) {
      return codeMessage;
    }
    return switch (exception.kind) {
      AppExceptionKind.networkUnavailable => '网络不可用，请检查连接',
      AppExceptionKind.timeout => '请求超时，请稍后重试',
      AppExceptionKind.cancelled => '',
      AppExceptionKind.rateLimited => '操作过于频繁，请稍后再试',
      AppExceptionKind.serviceUnavailable ||
      AppExceptionKind.serverError => '服务暂不可用，请稍后重试',
      AppExceptionKind.validation ||
      AppExceptionKind.badRequest => exception.detail ?? '输入内容不正确',
      _ => '操作失败，请稍后重试',
    };
  }
}
