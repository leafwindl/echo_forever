import 'package:flutter/material.dart';

enum CharacterDisplayState { idle, sitting, listening, thinking, speaking }

abstract class CharacterRenderer extends StatelessWidget {
  const CharacterRenderer({required this.state, super.key});

  final CharacterDisplayState state;
}

class StaticCharacterRenderer extends CharacterRenderer {
  const StaticCharacterRenderer({required super.state, super.key});

  static const idleAsset = 'assets/character/echo_idle.png';
  static const sittingAsset = 'assets/character/idle_sit.png';

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final isSitting = state == CharacterDisplayState.sitting;
    final assetPath = isSitting ? sittingAsset : idleAsset;
    final imageKey = isSitting
        ? const Key('character-sitting-image')
        : const Key('character-idle-image');
    final scale = switch (state) {
      CharacterDisplayState.sitting => 1.12,
      CharacterDisplayState.listening => 1.02,
      CharacterDisplayState.thinking => 0.98,
      CharacterDisplayState.speaking => 1.04,
      CharacterDisplayState.idle => 1.0,
    };
    final opacity = state == CharacterDisplayState.thinking ? 0.9 : 1.0;
    final background = Color.alphaBlend(
      colorScheme.primary.withValues(alpha: 0.07),
      colorScheme.surface,
    );

    return Semantics(
      label: state.semanticsLabel,
      image: true,
      child: ColoredBox(
        color: background,
        child: ClipRect(
          child: AnimatedPadding(
            duration: const Duration(milliseconds: 260),
            curve: Curves.easeOutCubic,
            padding: EdgeInsets.fromLTRB(
              isSitting ? 4 : 20,
              isSitting ? 0 : 10,
              isSitting ? 4 : 20,
              0,
            ),
            child: AnimatedOpacity(
              duration: const Duration(milliseconds: 220),
              opacity: opacity,
              child: AnimatedScale(
                duration: const Duration(milliseconds: 280),
                curve: Curves.easeOutCubic,
                scale: scale,
                alignment: Alignment.bottomCenter,
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 260),
                  switchInCurve: Curves.easeOutCubic,
                  switchOutCurve: Curves.easeInCubic,
                  transitionBuilder: (child, animation) {
                    return FadeTransition(
                      opacity: animation,
                      child: ScaleTransition(
                        scale: Tween<double>(begin: 0.96, end: 1).animate(
                          CurvedAnimation(
                            parent: animation,
                            curve: Curves.easeOutCubic,
                          ),
                        ),
                        child: child,
                      ),
                    );
                  },
                  child: Image.asset(
                    assetPath,
                    key: imageKey,
                    width: double.infinity,
                    height: double.infinity,
                    fit: BoxFit.contain,
                    alignment: Alignment.bottomCenter,
                    filterQuality: FilterQuality.high,
                    gaplessPlayback: true,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

extension on CharacterDisplayState {
  String get semanticsLabel => switch (this) {
    CharacterDisplayState.idle => 'Echo 角色',
    CharacterDisplayState.sitting => 'Echo 角色，聊天已展开',
    CharacterDisplayState.listening => 'Echo 角色，正在聆听',
    CharacterDisplayState.thinking => 'Echo 角色，正在思考',
    CharacterDisplayState.speaking => 'Echo 角色，正在说话',
  };
}
