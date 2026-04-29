import 'dart:math' as math;

import 'package:flutter/material.dart';

class StreakGeneWidget extends StatefulWidget {
  const StreakGeneWidget({
    super.key,
    required this.days,
    this.height = 92,
    this.progressionStep = 0,
    this.compact = false,
  });

  final List<bool> days;
  final double height;
  final int progressionStep;
  final bool compact;

  @override
  State<StreakGeneWidget> createState() => _StreakGeneWidgetState();
}

class _StreakGeneWidgetState extends State<StreakGeneWidget>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3600),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final radius = widget.compact ? 5.0 : 7.0;
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Container(
        height: widget.height,
        decoration: BoxDecoration(
          color: const Color(0xFF0B1022),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white10),
        ),
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, child) {
            final shift = (_controller.value * 22) + (widget.progressionStep * 8);
            return CustomPaint(
              painter: _StreakGenePainter(
                days: widget.days,
                animationShift: shift,
                radius: radius,
              ),
              child: const SizedBox.expand(),
            );
          },
        ),
      ),
    );
  }
}

class _StreakGenePainter extends CustomPainter {
  const _StreakGenePainter({
    required this.days,
    required this.animationShift,
    required this.radius,
  });

  final List<bool> days;
  final double animationShift;
  final double radius;

  static const _active = Color(0xFF4C6FFF);
  static const _inactive = Color(0xFF56607A);

  @override
  void paint(Canvas canvas, Size size) {
    final centerY = size.height / 2;
    final topY = centerY - (size.height * 0.24);
    final bottomY = centerY + (size.height * 0.24);
    final count = days.length.clamp(1, 10);
    final spacing = size.width / (count + 1);

    final helixA = Path();
    final helixB = Path();
    for (var i = 0; i <= count + 2; i++) {
      final x = (i * spacing) - (animationShift % spacing);
      final wave = math.sin((x / size.width) * math.pi * 2) * (size.height * 0.06);
      final yA = topY + wave;
      final yB = bottomY - wave;
      if (i == 0) {
        helixA.moveTo(x, yA);
        helixB.moveTo(x, yB);
      } else {
        helixA.lineTo(x, yA);
        helixB.lineTo(x, yB);
      }
    }

    final linePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = _active.withValues(alpha: 0.35);
    canvas.drawPath(helixA, linePaint);
    canvas.drawPath(helixB, linePaint);

    final rungPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..color = Colors.white24;

    for (var i = 0; i < count; i++) {
      final x = spacing * (i + 1);
      final completed = days[i];
      final isTop = i.isEven;
      final y = isTop ? topY : bottomY;
      final otherY = isTop ? bottomY : topY;

      canvas.drawLine(Offset(x, y), Offset(x, otherY), rungPaint);

      final fillPaint = Paint()
        ..style = PaintingStyle.fill
        ..color = completed ? _active : Colors.transparent;
      final borderPaint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = completed ? _active.withValues(alpha: 0.95) : _inactive;

      canvas.drawCircle(Offset(x, y), radius, fillPaint);
      canvas.drawCircle(Offset(x, y), radius, borderPaint);

      if (completed) {
        final glow = Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 5
          ..color = _active.withValues(alpha: 0.25)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
        canvas.drawCircle(Offset(x, y), radius, glow);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _StreakGenePainter oldDelegate) {
    return oldDelegate.days != days ||
        oldDelegate.animationShift != animationShift ||
        oldDelegate.radius != radius;
  }
}
