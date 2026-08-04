import 'package:audio_session/audio_session.dart';

import 'package:echo_app/features/call/domain/call_adapters.dart';

class SystemAudioSessionAdapter implements AudioSessionAdapter {
  AudioSession? _session;

  Future<AudioSession> _getSession() async =>
      _session ??= await AudioSession.instance;

  @override
  Future<void> configure() async {
    final session = await _getSession();
    await session.configure(const AudioSessionConfiguration.speech());
  }

  @override
  Future<void> beginRecording() async {
    final session = await _getSession();
    await session.configure(const AudioSessionConfiguration.speech());
    final activated = await session.setActive(true);
    if (!activated) throw StateError('无法获取录音音频焦点');
  }

  @override
  Future<void> beginPlayback() async {
    final session = await _getSession();
    await session.configure(const AudioSessionConfiguration.speech());
    final activated = await session.setActive(true);
    if (!activated) throw StateError('无法获取播放音频焦点');
  }

  @override
  Future<void> release() async {
    final session = await _getSession();
    await session.setActive(false);
  }

  @override
  Stream<bool> get interruptionStream async* {
    final session = await _getSession();
    yield* session.interruptionEventStream.map((event) => event.begin);
  }
}
