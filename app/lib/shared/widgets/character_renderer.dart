import 'package:flutter/material.dart';

abstract class CharacterRenderer extends StatelessWidget {
  const CharacterRenderer({required this.chatExpanded, super.key});

  final bool chatExpanded;
}

class StaticCharacterRenderer extends CharacterRenderer {
  const StaticCharacterRenderer({required super.chatExpanded, super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Semantics(
      label: 'Echo 静态角色占位',
      image: true,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 240),
        margin: EdgeInsets.symmetric(
          horizontal: chatExpanded ? 48 : 32,
          vertical: chatExpanded ? 8 : 16,
        ),
        decoration: BoxDecoration(
          color: colorScheme.primaryContainer,
          borderRadius: BorderRadius.circular(36),
        ),
        alignment: Alignment.center,
        child: Icon(
          Icons.auto_awesome_rounded,
          color: colorScheme.onPrimaryContainer,
          size: chatExpanded ? 52 : 76,
        ),
      ),
    );
  }
}
