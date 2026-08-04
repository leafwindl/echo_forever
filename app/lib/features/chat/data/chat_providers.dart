import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/features/chat/data/chat_api.dart';
import 'package:echo_app/features/chat/data/chat_repository_impl.dart';
import 'package:echo_app/features/chat/domain/chat_repository.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final chatApiProvider = Provider<ChatApi>((ref) {
  return ChatApi(ref.watch(authenticatedDioClientProvider));
});

final chatRepositoryProvider = Provider<ChatRepository>((ref) {
  return ChatRepositoryImpl(ref.watch(chatApiProvider));
});
