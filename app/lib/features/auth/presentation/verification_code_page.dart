import 'dart:async';
import 'dart:math';

import 'package:echo_app/core/errors/error_message_mapper.dart';
import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/auth/domain/phone_verification.dart';
import 'package:echo_app/features/auth/presentation/auth_controller.dart';
import 'package:echo_app/shared/utils/input_validators.dart';
import 'package:echo_app/shared/widgets/primary_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class VerificationCodePage extends ConsumerStatefulWidget {
  const VerificationCodePage({required this.verification, super.key});

  final PhoneVerification verification;

  @override
  ConsumerState<VerificationCodePage> createState() =>
      _VerificationCodePageState();
}

class _VerificationCodePageState extends ConsumerState<VerificationCodePage> {
  final _formKey = GlobalKey<FormState>();
  final _codeController = TextEditingController();
  late PhoneVerification _verification;
  Timer? _timer;
  var _resendSeconds = 0;

  @override
  void initState() {
    super.initState();
    _verification = widget.verification;
    _startCountdown();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _codeController.dispose();
    super.dispose();
  }

  void _startCountdown() {
    _timer?.cancel();
    _updateCountdown();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) {
        return;
      }
      setState(_updateCountdown);
    });
  }

  void _updateCountdown() {
    _resendSeconds = max(
      0,
      _verification.resendAt.difference(DateTime.now().toUtc()).inSeconds,
    );
    if (_resendSeconds == 0) {
      _timer?.cancel();
    }
  }

  Future<void> _verify() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    final success = await ref
        .read(authControllerProvider.notifier)
        .verifyCode(
          verification: _verification,
          code: _codeController.text.trim(),
        );
    if (mounted && success) {
      context.goNamed(RouteNames.home);
    }
  }

  Future<void> _resend() async {
    if (_resendSeconds > 0) {
      return;
    }
    final verification = await ref
        .read(authControllerProvider.notifier)
        .requestCode(_verification.phone);
    if (mounted && verification != null) {
      setState(() {
        _verification = verification;
        _codeController.clear();
      });
      _startCountdown();
    }
  }

  void _changePhone() {
    ref.read(authControllerProvider.notifier).resetVerification();
    context.goNamed(RouteNames.login);
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final error = authState.error;

    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: _changePhone),
        title: const Text('输入验证码'),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Text(
                      '验证码已发送至',
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _verification.phoneMasked,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 28),
                    TextFormField(
                      controller: _codeController,
                      autofocus: true,
                      keyboardType: TextInputType.number,
                      textInputAction: TextInputAction.done,
                      autofillHints: const <String>[AutofillHints.oneTimeCode],
                      inputFormatters: <TextInputFormatter>[
                        FilteringTextInputFormatter.digitsOnly,
                        LengthLimitingTextInputFormatter(6),
                      ],
                      decoration: const InputDecoration(
                        labelText: '6 位验证码',
                        hintText: '000000',
                      ),
                      validator: InputValidators.verificationCode,
                      onFieldSubmitted: (_) => _verify(),
                    ),
                    if (error != null) ...<Widget>[
                      const SizedBox(height: 12),
                      Text(
                        ErrorMessageMapper.toChinese(error),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    const SizedBox(height: 20),
                    PrimaryButton(
                      label: '登录',
                      isLoading:
                          authState.operation == AuthOperation.verifyingCode,
                      onPressed: _verify,
                    ),
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: authState.isBusy || _resendSeconds > 0
                          ? null
                          : _resend,
                      child: Text(
                        _resendSeconds > 0
                            ? '$_resendSeconds 秒后可重新发送'
                            : '重新发送验证码',
                      ),
                    ),
                    TextButton(
                      onPressed: _changePhone,
                      child: const Text('更换手机号'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
