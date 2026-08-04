import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/features/call/data/call_audio_engine.dart';
import 'package:echo_app/features/call/data/call_chat_client.dart';
import 'package:echo_app/features/call/data/record_recorder_adapter.dart';
import 'package:echo_app/features/call/data/system_audio_session_adapter.dart';
import 'package:echo_app/features/call/data/temp_audio_store.dart';
import 'package:echo_app/features/call/data/voice_upload_client.dart';
import 'package:echo_app/features/call/data/web_socket_voice_client.dart';
import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/chat/data/chat_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final recorderAdapterProvider = Provider<RecorderAdapter>((ref) {
  final adapter = RecordRecorderAdapter();
  ref.onDispose(adapter.dispose);
  return adapter;
});

final voiceSocketClientProvider = Provider<VoiceSocketClient>((ref) {
  final session = ref.watch(sessionControllerProvider).asData?.value;
  return WebSocketVoiceClient(
    baseUrl: ref.watch(appConfigProvider).baseUrl,
    accessToken: session?.accessToken ?? '',
  );
});

final voiceUploadClientProvider = Provider<VoiceUploadClient>((ref) {
  // A verified PcmUploadTranscoder can be injected here by deployments where
  // /voice/asr remains MP3-only. The default never labels PCM as audio/mpeg.
  return DioVoiceUploadClient(ref.watch(authenticatedDioClientProvider));
});

final callChatClientProvider = Provider<CallChatClient>((ref) {
  return ApiCallChatClient(ref.watch(chatApiProvider));
});

final callAudioEngineProvider = Provider<CallAudioEngine>((ref) {
  final engine = CallAudioEngine();
  ref.onDispose(engine.dispose);
  return engine;
});

final audioPlayerAdapterProvider = Provider<AudioPlayerAdapter>((ref) {
  return ref.watch(callAudioEngineProvider);
});

final callForegroundServiceProvider = Provider<CallForegroundService>((ref) {
  return ref.watch(callAudioEngineProvider);
});

final audioSessionAdapterProvider = Provider<AudioSessionAdapter>((ref) {
  return SystemAudioSessionAdapter();
});

final tempAudioStoreProvider = Provider<TempAudioStore>((ref) {
  return const TempAudioStore();
});
