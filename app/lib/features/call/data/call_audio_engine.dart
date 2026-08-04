import 'dart:async';

import 'package:audio_service/audio_service.dart';
import 'package:echo_app/features/call/domain/audio_segment_queue.dart';
import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:just_audio/just_audio.dart';

/// One player is shared by foreground-service controls and the call state
/// machine. just_audio's lazy playlist preparation starts the first segment as
/// soon as it is playable and prepares the following segment in order.
class CallAudioEngine implements AudioPlayerAdapter, CallForegroundService {
  _CallAudioHandler? _handler;
  Future<_CallAudioHandler>? _opening;

  Future<_CallAudioHandler> _open() {
    return _opening ??= AudioService.init<_CallAudioHandler>(
      builder: _CallAudioHandler.new,
      config: const AudioServiceConfig(
        androidNotificationChannelId: 'cn.echoaiforever.echo.call',
        androidNotificationChannelName: 'Echo 通话',
        androidNotificationOngoing: true,
        androidStopForegroundOnPause: true,
      ),
    ).then((handler) => _handler = handler);
  }

  @override
  Future<void> start({required Future<void> Function() onStopRequested}) async {
    final handler = await _open();
    handler.activateCall(onStopRequested);
  }

  @override
  Future<void> playSegments(
    List<String> urls, {
    required bool Function() shouldContinue,
  }) async {
    final safeUrls = AudioSegmentQueue.sanitize(urls);
    if (safeUrls.isEmpty || !shouldContinue()) return;
    final handler = await _open();
    await handler.playSegments(safeUrls, shouldContinue: shouldContinue);
  }

  @override
  Future<void> stop() async {
    await _handler?.stopPlaybackOnly();
  }

  @override
  Future<void> stopService() async {
    await _handler?.endCall();
  }

  @override
  Future<void> dispose() async {
    await _handler?.disposePlayer();
    _handler = null;
    _opening = null;
  }
}

class _CallAudioHandler extends BaseAudioHandler {
  _CallAudioHandler() {
    _player.playbackEventStream.listen(
      _broadcastPlaybackState,
      onError: (Object _) {
        playbackState.add(
          playbackState.value.copyWith(
            playing: false,
            processingState: AudioProcessingState.error,
          ),
        );
      },
    );
  }

  final AudioPlayer _player = AudioPlayer(useLazyPreparation: true);
  Future<void> Function()? _onStopRequested;

  void activateCall(Future<void> Function() onStopRequested) {
    _onStopRequested = onStopRequested;
    mediaItem.add(
      const MediaItem(
        id: 'echo-active-call',
        title: 'Echo 通话中',
        artist: '点击结束可安全挂断',
      ),
    );
    playbackState.add(
      playbackState.value.copyWith(
        controls: const <MediaControl>[MediaControl.stop],
        processingState: AudioProcessingState.ready,
        playing: false,
      ),
    );
  }

  Future<void> playSegments(
    List<Uri> urls, {
    required bool Function() shouldContinue,
  }) async {
    final sources = urls.map(AudioSource.uri).toList(growable: false);
    Object? firstFailure;
    for (var attempt = 0; attempt < 2; attempt += 1) {
      if (!shouldContinue()) return;
      try {
        await _player.setAudioSources(sources, preload: true);
        if (!shouldContinue()) return;
        await _player.play();
        return;
      } on PlayerInterruptedException {
        rethrow;
      } on Object catch (error) {
        firstFailure ??= error;
        if (attempt == 1) throw firstFailure;
        await _player.stop();
      }
    }
  }

  Future<void> stopPlaybackOnly() async {
    await _player.stop();
    playbackState.add(
      playbackState.value.copyWith(
        controls: const <MediaControl>[MediaControl.stop],
        playing: false,
        processingState: AudioProcessingState.ready,
      ),
    );
  }

  @override
  Future<void> stop() async {
    await stopPlaybackOnly();
    final callback = _onStopRequested;
    if (callback != null) await callback();
  }

  Future<void> endCall() async {
    _onStopRequested = null;
    await _player.stop();
    mediaItem.add(null);
    playbackState.add(
      playbackState.value.copyWith(
        controls: const <MediaControl>[],
        playing: false,
        processingState: AudioProcessingState.idle,
      ),
    );
  }

  Future<void> disposePlayer() async {
    await endCall();
    await _player.dispose();
  }

  void _broadcastPlaybackState(PlaybackEvent event) {
    playbackState.add(
      PlaybackState(
        controls: const <MediaControl>[MediaControl.stop],
        androidCompactActionIndices: const <int>[0],
        processingState: switch (_player.processingState) {
          ProcessingState.idle => AudioProcessingState.idle,
          ProcessingState.loading => AudioProcessingState.loading,
          ProcessingState.buffering => AudioProcessingState.buffering,
          ProcessingState.ready => AudioProcessingState.ready,
          ProcessingState.completed => AudioProcessingState.completed,
        },
        playing: _player.playing,
        updatePosition: _player.position,
        bufferedPosition: _player.bufferedPosition,
        speed: _player.speed,
        queueIndex: event.currentIndex,
      ),
    );
  }
}
