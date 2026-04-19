
import 'package:flutter/material.dart';

/// General recommendation shown on the dashboard; schedule and duration are set on the detail screen.
class AdviceDetailData {
  const AdviceDetailData({
    required this.title,
    required this.summary,
    required this.icon,
  });

  final String title;
  final String summary;
  final IconData icon;
}
