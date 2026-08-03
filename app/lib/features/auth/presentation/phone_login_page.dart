import 'package:echo_app/core/errors/error_message_mapper.dart';
import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/auth/presentation/auth_controller.dart';
import 'package:echo_app/shared/utils/input_validators.dart';
import 'package:echo_app/shared/widgets/primary_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class PhoneLoginPage extends ConsumerStatefulWidget {
  const PhoneLoginPage({super.key});

  @override
  ConsumerState<PhoneLoginPage> createState() => _PhoneLoginPageState();
}

class _PhoneLoginPageState extends ConsumerState<PhoneLoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _phoneController = TextEditingController();

  @override
  void dispose() {
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    final phone = InputValidators.normalizeMainlandPhone(_phoneController.text);
    final verification = await ref
        .read(authControllerProvider.notifier)
        .requestCode(phone);
    if (mounted && verification != null) {
      context.goNamed(RouteNames.verification);
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final error = authState.error;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Text(
                      'Echo',
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      '用手机号继续',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '我们会向你的中国大陆手机号发送 6 位验证码。',
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 28),
                    TextFormField(
                      controller: _phoneController,
                      autofocus: true,
                      keyboardType: TextInputType.phone,
                      textInputAction: TextInputAction.done,
                      autofillHints: const <String>[
                        AutofillHints.telephoneNumber,
                      ],
                      inputFormatters: <TextInputFormatter>[
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9+\s-]')),
                        LengthLimitingTextInputFormatter(20),
                      ],
                      decoration: const InputDecoration(
                        labelText: '手机号',
                        hintText: '138 0013 8000',
                        prefixText: '+86  ',
                      ),
                      validator: InputValidators.mainlandPhone,
                      onFieldSubmitted: (_) => _submit(),
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
                      label: '获取验证码',
                      isLoading:
                          authState.operation == AuthOperation.sendingCode,
                      onPressed: _submit,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      '继续即表示你同意 Echo 的服务条款与隐私政策。',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall,
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
