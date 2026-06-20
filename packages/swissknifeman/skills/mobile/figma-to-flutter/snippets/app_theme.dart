// Source: tokens.json (из figma-mcp-core) → Flutter ThemeData. Генерируется из токенов, не вручную.
import 'package:flutter/material.dart';

/// Дизайн-токены из Figma Variables. Имена сохраняют семантику Figma-переменных.
abstract class AppTokens {
  // color.* (mode: light)
  static const primary = Color(0xFF3B82F6); // figma:variable/Primary/Blue-500
  static const surface = Color(0xFFFFFFFF);
  static const surfaceElevated = Color(0xFFF8FAFC);

  // color.* (mode: dark)
  static const primaryDark = Color(0xFF60A5FA);
  static const surfaceDark = Color(0xFF0F172A);
  static const surfaceElevatedDark = Color(0xFF1E293B);

  // border-radius.*
  static const radiusSm = 4.0;
  static const radiusMd = 8.0;
}

ThemeData _base(ColorScheme scheme) => ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      fontFamily: 'Inter',
      // typography.heading-1
      textTheme: const TextTheme(
        displayLarge: TextStyle(fontSize: 32, height: 40 / 32, fontWeight: FontWeight.w700),
      ),
    );

final lightTheme = _base(
  const ColorScheme.light(primary: AppTokens.primary, surface: AppTokens.surface),
);

final darkTheme = _base(
  const ColorScheme.dark(primary: AppTokens.primaryDark, surface: AppTokens.surfaceDark),
);

// MaterialApp(theme: lightTheme, darkTheme: darkTheme, themeMode: ThemeMode.system)
