import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/features/presence/domain/presence.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final presenceProvider = FutureProvider.autoDispose<PresenceSnapshot>((ref) {
  return ref.watch(presenceRepositoryProvider).getPresence();
});
