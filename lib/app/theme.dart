import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

const rootLinkBlue = Color(0xFF5578E7);

ThemeData buildRootLinkTheme({required bool dark}) {
  final generated = ColorScheme.fromSeed(
    seedColor: rootLinkBlue,
    brightness: dark ? Brightness.dark : Brightness.light,
  );
  final scheme = generated.copyWith(
    primary: dark ? const Color(0xFF7695F5) : const Color(0xFF456BE0),
    onPrimary: Colors.white,
    surface: dark ? const Color(0xFF171719) : Colors.white,
    surfaceContainer: dark ? const Color(0xFF202023) : const Color(0xFFF0F1F3),
    surfaceContainerHighest: dark
        ? const Color(0xFF29292D)
        : const Color(0xFFE8E9EC),
    outline: dark ? const Color(0xFF3B3B40) : const Color(0xFFD5D7DC),
    outlineVariant: dark ? const Color(0xFF2D2D31) : const Color(0xFFE2E3E7),
    onSurface: dark ? const Color(0xFFF4F4F5) : const Color(0xFF18181B),
    onSurfaceVariant: dark ? const Color(0xFFB5B5BA) : const Color(0xFF626269),
  );
  final base = ThemeData(
    useMaterial3: true,
    brightness: scheme.brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: dark
        ? const Color(0xFF0D0D0E)
        : const Color(0xFFF7F7F8),
    fontFamilyFallback: const <String>[
      'SF Pro Display',
      'PingFang SC',
      'Microsoft YaHei',
    ],
  );
  final border = OutlineInputBorder(
    borderRadius: BorderRadius.circular(18),
    borderSide: BorderSide.none,
  );
  return base.copyWith(
    cupertinoOverrideTheme: CupertinoThemeData(
      brightness: scheme.brightness,
      primaryColor: scheme.primary,
      scaffoldBackgroundColor: base.scaffoldBackgroundColor,
    ),
    appBarTheme: AppBarTheme(
      centerTitle: false,
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: Colors.transparent,
      titleTextStyle: base.textTheme.titleLarge?.copyWith(
        color: scheme.onSurface,
        fontWeight: FontWeight.w700,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: scheme.surface,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainer,
      border: border,
      enabledBorder: border,
      focusedBorder: border.copyWith(
        borderSide: BorderSide(color: scheme.primary, width: 1.4),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: scheme.primary,
        foregroundColor: Colors.white,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      elevation: 0,
      backgroundColor: scheme.surface.withValues(alpha: 0.96),
      indicatorColor: scheme.primary.withValues(alpha: 0.14),
      height: 68,
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant.withValues(alpha: 0.45),
      thickness: 1,
    ),
  );
}
