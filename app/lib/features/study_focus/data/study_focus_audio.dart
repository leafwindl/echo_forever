import 'dart:async';

import 'package:audio_session/audio_session.dart';
import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';

class StudyFocusAudio {
  final AudioPlayer _rain = AudioPlayer();
  final AudioPlayer _writing = AudioPlayer();
  AudioSession? _session;
  Future<void>? _prepareFuture;

  Future<void> prepare() => _prepareFuture ??= _prepare();

  Future<void> _prepare() async {
    await Future.wait(<Future<void>>[
      _load(_rain, 'assets/study_focus/rain.mp3'),
      _load(_writing, 'assets/study_focus/writing.mp3'),
    ]);
    await Future.wait(<Future<void>>[
      _rain.setLoopMode(LoopMode.one),
      _writing.setLoopMode(LoopMode.one),
      _rain.setVolume(1),
      _writing.setVolume(1),
    ]);
  }

  Future<void> play() async {
    try {
      await _activateSession();
      await prepare();
      unawaited(_playSafely(_rain));
      unawaited(_playSafely(_writing));
    } on Object catch (error) {
      // A missing optional ambience asset must never block the timer.
      debugPrint('Study focus audio: prepare failed: $error');
    }
  }

  Future<void> pause() async {
    await Future.wait(<Future<void>>[
      _pauseSafely(_rain),
      _pauseSafely(_writing),
    ]);
  }

  Future<void> stop() async {
    await Future.wait(<Future<void>>[
      _stopSafely(_rain),
      _stopSafely(_writing),
    ]);
    await _releaseSession();
  }

  Future<void> dispose() async {
    await _releaseSession();
    await _rain.dispose();
    await _writing.dispose();
  }

  Future<void> _load(AudioPlayer player, String asset) async {
    try {
      await player.setAsset(asset);
    } on Object catch (error) {
      // Keep the other ambience track available when one asset is absent.
      debugPrint('Study focus audio: failed to load $asset: $error');
    }
  }

  Future<void> _activateSession() async {
    final session = _session ??= await AudioSession.instance;
    await session.configure(const AudioSessionConfiguration.music());
    await session.setActive(true);
  }

  Future<void> _playSafely(AudioPlayer player) async {
    try {
      await player.play();
    } on Object catch (error) {
      // Ambience playback is optional and must not affect the timer.
      debugPrint('Study focus audio: playback failed: $error');
    }
  }

  Future<void> _pauseSafely(AudioPlayer player) async {
    try {
      await player.pause();
    } on Object {
      // Keep timer controls usable if an audio backend is unavailable.
    }
  }

  Future<void> _stopSafely(AudioPlayer player) async {
    try {
      await player.stop();
      await player.seek(Duration.zero);
    } on Object {
      // Keep completion usable if an audio backend is unavailable.
    }
  }

  Future<void> _releaseSession() async {
    final session = _session;
    if (session == null) return;
    try {
      await session.setActive(false);
    } on Object {
      // Audio focus cleanup is best effort.
    }
  }
}
