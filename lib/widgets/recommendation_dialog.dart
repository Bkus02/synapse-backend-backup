import 'package:flutter/material.dart';

class RecommendationDialog extends StatelessWidget {
  final IconData icon;
  final String title;
  final String message;
  final VoidCallback onAccept;
  final VoidCallback onReject;

  const RecommendationDialog({
    super.key,
    this.icon = Icons.lightbulb_outline,
    required this.title,
    required this.message,
    required this.onAccept,
    required this.onReject,
  });

  static Future<void> show(
    BuildContext context, {
    required String title,
    required String message,
    required VoidCallback onAccept,
    required VoidCallback onReject,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => RecommendationDialog(
        title: title,
        message: message,
        onAccept: onAccept,
        onReject: onReject,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: theme.colorScheme.primary.withOpacity(0.12),
                  child: Icon(icon, color: theme.colorScheme.primary),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    title,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Text(message, style: theme.textTheme.bodyMedium),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: onReject,
                    child: const Text("Hayir, gerek yok"),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: ElevatedButton(
                    onPressed: onAccept,
                    child: const Text("Evet, lutfen"),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

