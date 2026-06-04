
import 'package:flutter/material.dart';

/// General recommendation shown on the dashboard; schedule and duration are
/// set on the detail dialog. ``adviceKey`` is the canonical key from the
/// backend ADVICE_CATALOG and is required to schedule the advice through
/// ``/advice-schedules``.
class AdviceDetailData {
  const AdviceDetailData({
    required this.title,
    required this.summary,
    required this.icon,
    this.adviceKey,
  });

  final String title;
  final String summary;
  final IconData icon;
  final String? adviceKey;
}
