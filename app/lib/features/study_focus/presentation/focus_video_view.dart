import 'dart:async';

import 'package:echo_app/shared/widgets/character_renderer.dart';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

class FocusVideoView extends StatefulWidget {
  const FocusVideoView({required this.playing, super.key});

  final bool playing;

  @override
  State<FocusVideoView> createState() => _FocusVideoViewState();
}

class _FocusVideoViewState extends State<FocusVideoView> {
  late final VideoPlayerController _controller;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _controller = VideoPlayerController.asset(
      'assets/study_focus/echo_study.mp4',
      videoPlayerOptions: VideoPlayerOptions(mixWithOthers: true),
    );
    _initialize();
  }

  @override
  void didUpdateWidget(covariant FocusVideoView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!_controller.value.isInitialized) return;
    unawaited(_syncPlayback());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _initialize() async {
    try {
      await _controller.initialize();
      await _controller.setLooping(true);
      await _controller.setVolume(0);
      await _syncPlayback();
      if (mounted) setState(() {});
    } on Object catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  Future<void> _syncPlayback() async {
    if (!_controller.value.isInitialized) return;
    if (widget.playing) {
      await _controller.play();
    } else {
      await _controller.pause();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return const ColoredBox(
        color: Color(0xFF182124),
        child: Center(
          child: StaticCharacterRenderer(state: CharacterDisplayState.sitting),
        ),
      );
    }
    if (!_controller.value.isInitialized) {
      return const ColoredBox(color: Color(0xFF182124));
    }
    return FittedBox(
      fit: BoxFit.cover,
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        width: _controller.value.size.width,
        height: _controller.value.size.height,
        child: VideoPlayer(_controller),
      ),
    );
  }
}
