import 'package:flutter/material.dart';

/// Light, airy palette inspired by clean habit-tracking UIs.
abstract final class AppColors {
  static const scaffold = Color(0xFFF8FAFC);
  static const surface = Color(0xFFFFFFFF);
  static const surfaceMuted = Color(0xFFF1F5F9);
  static const inputFill = Color(0xFFF1F5F9);
  static const segmentedInactive = Color(0xFFE8ECF0);

  static const textPrimary = Color(0xFF1A2744);
  static const textSecondary = Color(0xFF64748B);
  static const textMuted = Color(0xFF94A3B8);
  static const textOnAccent = Color(0xFFFFFFFF);

  static const accent = Color(0xFF4A90E2);
  static const accentLight = Color(0xFFE3F2FD);
  static const accentSoft = Color(0xFFB3D4F5);

  static const border = Color(0xFFE2E8F0);
  static const borderStrong = Color(0xFFCBD5E1);

  static const error = Color(0xFFE53935);
  static const warning = Color(0xFFFFB300);
  static const success = Color(0xFF43A047);

  static const modalBarrier = Color(0x66000000);

  static List<BoxShadow> get cardShadow => [
        BoxShadow(
          color: textPrimary.withValues(alpha: 0.06),
          blurRadius: 12,
          offset: const Offset(0, 4),
        ),
      ];

  static BoxDecoration cardDecoration({double radius = 16}) => BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: cardShadow,
      );
}
