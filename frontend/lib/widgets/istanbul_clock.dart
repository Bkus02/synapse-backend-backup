import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Live clock pinned in the dashboard AppBar that always shows the current
/// time in Türkiye (Europe/Istanbul). Turkey has been on a fixed UTC+3
/// offset since 2016, so we don't need a timezone database — just shift
/// the device's UTC time by +3 hours and re-render every second.
class IstanbulClock extends StatefulWidget {
  const IstanbulClock({super.key, this.compact = false});

  final bool compact;

  @override
  State<IstanbulClock> createState() => _IstanbulClockState();
}

class _IstanbulClockState extends State<IstanbulClock> {
  static const Duration _istanbulOffset = Duration(hours: 3);
  late Timer _ticker;
  late DateTime _now;

  @override
  void initState() {
    super.initState();
    _now = _computeIstanbulNow();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() => _now = _computeIstanbulNow());
    });
  }

  @override
  void dispose() {
    _ticker.cancel();
    super.dispose();
  }

  DateTime _computeIstanbulNow() {
    return DateTime.now().toUtc().add(_istanbulOffset);
  }

  String _format(DateTime dt) {
    final hh = dt.hour.toString().padLeft(2, '0');
    final mm = dt.minute.toString().padLeft(2, '0');
    final ss = dt.second.toString().padLeft(2, '0');
    return widget.compact ? '$hh:$mm' : '$hh:$mm:$ss';
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: AppColors.surfaceMuted,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
            color: AppColors.border.withValues(alpha: 0.6),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.schedule_rounded,
              size: 14,
              color: AppColors.textSecondary,
            ),
            const SizedBox(width: 6),
            Text(
              _format(_now),
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
            const SizedBox(width: 6),
            Text(
              'IST',
              style: TextStyle(
                color: AppColors.textSecondary.withValues(alpha: 0.85),
                fontSize: 10,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.4,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
