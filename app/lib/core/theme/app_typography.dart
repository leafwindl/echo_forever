import 'package:echo_app/core/theme/app_colors.dart';
import 'package:flutter/material.dart';

class AppTypography {
  const AppTypography._();

  static const textTheme = TextTheme(
    headlineMedium: TextStyle(
      color: AppColors.ink,
      fontSize: 30,
      fontWeight: FontWeight.w700,
    ),
    titleLarge: TextStyle(
      color: AppColors.ink,
      fontSize: 20,
      fontWeight: FontWeight.w600,
    ),
    bodyLarge: TextStyle(color: AppColors.ink, fontSize: 16, height: 1.5),
  );
}
