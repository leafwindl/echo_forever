import 'package:echo_app/core/auth_session/session_snapshot.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

String? authRedirect({
  required String location,
  required AsyncValue<SessionSnapshot> session,
  required bool hasVerification,
}) {
  if (session.isLoading) {
    return location == '/splash' ? null : '/splash';
  }
  final isAuthenticated = session.asData?.value.isAuthenticated ?? false;
  final isAuthLocation = location == '/login' || location == '/verify';
  if (isAuthenticated) {
    return isAuthLocation || location == '/splash' ? '/home' : null;
  }
  if (location == '/verify' && hasVerification) {
    return null;
  }
  return location == '/login' ? null : '/login';
}
