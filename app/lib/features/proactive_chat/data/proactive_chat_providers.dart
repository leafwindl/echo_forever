import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/features/proactive_chat/data/proactive_chat_api.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final proactiveChatApiProvider = Provider<ProactiveChatApi>((ref) {
  return ProactiveChatApi(ref.watch(authenticatedDioClientProvider));
});
