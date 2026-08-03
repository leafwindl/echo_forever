import 'package:echo_app/core/auth_session/session_events.dart';
import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class SessionController extends AsyncNotifier<SessionSnapshot> {
  @override
  Future<SessionSnapshot> build() {
    return ref.read(secureStoreProvider).readSession();
  }

  SessionSnapshot? get current => state.asData?.value;

  Future<void> establish(SessionSnapshot snapshot) async {
    await ref.read(secureStoreProvider).writeSession(snapshot);
    state = AsyncData(snapshot);
  }

  void markOnline() {
    final snapshot = current;
    if (snapshot?.isAuthenticated ?? false) {
      state = AsyncData(
        snapshot!.copyWithAvailability(SessionAvailability.online),
      );
    }
  }

  void markTemporarilyOffline() {
    final snapshot = current;
    if (snapshot?.isAuthenticated ?? false) {
      state = AsyncData(
        snapshot!.copyWithAvailability(SessionAvailability.temporarilyOffline),
      );
    }
  }

  Future<void> signOut(SessionEndReason reason) async {
    await ref.read(secureStoreProvider).clearSession();
    state = const AsyncData(SessionSnapshot.signedOut());
  }
}

final sessionControllerProvider =
    AsyncNotifierProvider<SessionController, SessionSnapshot>(
      SessionController.new,
    );
