// Source: tokens.json spacing.* → типизированный доступ. Замена магическим числам отступов.
import 'package:flutter/widgets.dart';

/// spacing.* из Figma Variables (4px grid). Использовать вместо литералов в Padding/SizedBox.
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

// Пример: Padding(padding: EdgeInsets.all(context.space.md), child: ...)
// itemSpacing из Figma → Column(spacing: context.space.sm, children: [...])  // Flutter 3.27+
