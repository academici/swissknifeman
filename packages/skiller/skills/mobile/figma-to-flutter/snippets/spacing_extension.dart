// Source: tokens.json spacing.* → typed access. Replacement for magic indentation numbers.
import 'package:flutter/widgets.dart';

/// spacing.* from Figma Variables (4px grid). Use instead of literals in Padding/SizedBox.
@immutable
class AppSpacing {
  const AppSpacing();
  final double xs = 4;
  final double sm = 8;
  final double md = 16;
  final double lg = 24;
  final double xl = 32;
}

const spacing = AppSpacing();

extension AppSpacingContext on BuildContext {
  AppSpacing get space => spacing;
}

// Example: Padding(padding: EdgeInsets.all(context.space.md), child: ...)
// itemSpacing from Figma → Column(spacing: context.space.sm, children: [...])  // Flutter 3.27+
