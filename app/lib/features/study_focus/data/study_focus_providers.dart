import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/features/study_focus/data/study_focus_api.dart';
import 'package:echo_app/features/study_focus/data/study_focus_audio.dart';
import 'package:echo_app/features/study_focus/data/study_focus_local_store.dart';
import 'package:echo_app/features/study_focus/data/study_focus_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final studyFocusLocalStoreProvider = Provider<StudyFocusLocalStore>(
  (ref) => StudyFocusLocalStore(),
);

final studyFocusApiProvider = Provider<StudyFocusApi>(
  (ref) => StudyFocusApi(ref.watch(authenticatedDioClientProvider)),
);

final studyFocusNotificationServiceProvider =
    Provider<StudyFocusNotificationService>(
      (ref) => StudyFocusNotificationService(),
    );

final studyFocusAudioProvider = Provider<StudyFocusAudio>((ref) {
  final audio = StudyFocusAudio();
  ref.onDispose(() {
    audio.dispose();
  });
  return audio;
});
