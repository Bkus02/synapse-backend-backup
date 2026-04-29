import 'package:flutter/material.dart';

import '../services/environment_api.dart';
import '../services/join_request_inbox.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';

/// In-app notifications: optional “home tips” (demo) + real join requests with
/// Approve / Reject and a shortcut to the environment approval screen.
class NotificationsModal {
  NotificationsModal._();

  static const _sheetColor = Color(0xFF0C1021);
  static const _cardColor = Color(0xFF1E2330);
  static const _accent = Color(0xFF4C6FFF);

  static Future<void> show(
    BuildContext context, {
    required void Function(String environmentId) onNavigateToEnvironmentApprovals,
    VoidCallback? onSheetClosed,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black54,
      builder: (sheetContext) {
        return _NotificationsSheet(
          sheetColor: _sheetColor,
          cardColor: _cardColor,
          accent: _accent,
          onNavigateToEnvironmentApprovals: (envId) {
            Navigator.pop(sheetContext);
            onNavigateToEnvironmentApprovals(envId);
          },
        );
      },
    ).whenComplete(() => onSheetClosed?.call());
  }
}

class _NotificationsSheet extends StatefulWidget {
  const _NotificationsSheet({
    required this.sheetColor,
    required this.cardColor,
    required this.accent,
    required this.onNavigateToEnvironmentApprovals,
  });

  final Color sheetColor;
  final Color cardColor;
  final Color accent;
  final void Function(String environmentId) onNavigateToEnvironmentApprovals;

  @override
  State<_NotificationsSheet> createState() => _NotificationsSheetState();
}

class _NotificationsSheetState extends State<_NotificationsSheet> {
  static String _timeLabel(String? iso) {
    if (iso == null || iso.isEmpty) return 'Pending';
    try {
      final dt = DateTime.parse(iso);
      final diff = DateTime.now().difference(dt);
      if (diff.inMinutes < 1) return 'Just now';
      if (diff.inHours < 1) return '${diff.inMinutes} min ago';
      if (diff.inDays < 1) return '${diff.inHours} hr ago';
      if (diff.inDays < 7) return '${diff.inDays} d ago';
      return '${(diff.inDays / 7).floor()} wk ago';
    } catch (_) {
      return 'Pending';
    }
  }

  List<JoinRequestInboxItem> _joinItems = [];
  bool _loadingJoin = true;
  String? _joinError;

  final List<_TipEntry> _tips = [
    _TipEntry(
      icon: Icons.lightbulb,
      title: 'Energy Saving Mode',
      message:
          'Living room lights were dimmed by 20% based on your habits.',
      timeAgo: '2 min ago',
    ),
    _TipEntry(
      icon: Icons.ac_unit,
      title: 'Cooling Schedule',
      message:
          'AC was set to 22°C in the lounge based on your evening routine.',
      timeAgo: '18 min ago',
    ),
    _TipEntry(
      icon: Icons.lightbulb,
      title: 'Bedroom Lights',
      message: 'Bedroom lights were switched to night mode.',
      timeAgo: '1 hr ago',
    ),
  ];

  final Set<int> _busyRequestIds = {};

  @override
  void initState() {
    super.initState();
    _loadJoin();
  }

  Future<void> _loadJoin() async {
    setState(() {
      _loadingJoin = true;
      _joinError = null;
    });
    try {
      final list = await JoinRequestInbox.loadPendingForAdmin();
      if (mounted) {
        setState(() {
          _joinItems = list;
          _loadingJoin = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _joinError = e.toString();
          _loadingJoin = false;
        });
      }
    }
  }

  Future<void> _approve(JoinRequestInboxItem item) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    setState(() => _busyRequestIds.add(item.request.id));
    try {
      await EnvironmentApi.approveJoinRequest(
        environmentId: item.environment.id,
        requestId: item.request.id,
        adminUserId: uid,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Membership approved'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        await _loadJoin();
      }
    } on UserApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e.message),
            backgroundColor: Colors.redAccent,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _busyRequestIds.remove(item.request.id));
      }
    }
  }

  Future<void> _reject(JoinRequestInboxItem item) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    setState(() => _busyRequestIds.add(item.request.id));
    try {
      await EnvironmentApi.rejectJoinRequest(
        environmentId: item.environment.id,
        requestId: item.request.id,
        adminUserId: uid,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Request rejected'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        await _loadJoin();
      }
    } on UserApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e.message),
            backgroundColor: Colors.redAccent,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _busyRequestIds.remove(item.request.id));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final sheetHeight = media.size.height * 0.87;

    return Padding(
      padding: EdgeInsets.only(bottom: media.viewInsets.bottom),
      child: Align(
        alignment: Alignment.bottomCenter,
        child: ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(25)),
          child: Material(
            color: widget.sheetColor,
            child: SizedBox(
              height: sheetHeight,
              width: double.infinity,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 12),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Row(
                      children: [
                        Container(
                          width: 40,
                          height: 4,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.28),
                            borderRadius: BorderRadius.circular(999),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Text(
                            'Notifications',
                            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                        ),
                        IconButton(
                          onPressed: _loadJoin,
                          icon: const Icon(Icons.refresh_rounded),
                          color: widget.accent,
                          tooltip: 'Refresh',
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: ListView(
                      padding: const EdgeInsets.only(bottom: 24),
                      children: [
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 20),
                          child: Text(
                            'Join requests',
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(
                                  color: Colors.white70,
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        if (_loadingJoin)
                          const Padding(
                            padding: EdgeInsets.all(20),
                            child: Center(
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                          )
                        else if (_joinError != null)
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 20),
                            child: Text(
                              _joinError!,
                              style: const TextStyle(
                                color: Colors.redAccent,
                                fontSize: 12,
                              ),
                            ),
                          )
                        else if (_joinItems.isEmpty)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                            child: Text(
                              SessionService.instance.user == null
                                  ? 'Sign in to see join requests for environments you manage.'
                                  : 'No pending join requests.',
                              style: TextStyle(
                                color: Colors.white.withValues(alpha: 0.45),
                                fontSize: 14,
                              ),
                            ),
                          )
                        else
                          ..._joinItems.map((item) {
                            final busy =
                                _busyRequestIds.contains(item.request.id);
                            final who = item.request.requesterName
                                        ?.trim()
                                        .isNotEmpty ==
                                    true
                                ? item.request.requesterName!.trim()
                                : item.request.userId;
                            return Padding(
                              padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
                              child: Card(
                                color: widget.cardColor,
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(14),
                                ),
                                child: Padding(
                                  padding: const EdgeInsets.all(14),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Icon(
                                            Icons.person_add_alt_1_rounded,
                                            color: widget.accent,
                                            size: 26,
                                          ),
                                          const SizedBox(width: 10),
                                          const Expanded(
                                            child: Text(
                                              'Someone wants to join',
                                              style: TextStyle(
                                                color: Colors.white,
                                                fontSize: 16,
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        '$who asked to join "${item.environment.name}" (${item.environment.id}).',
                                        style: TextStyle(
                                          color: Colors.white
                                              .withValues(alpha: 0.72),
                                          fontSize: 14,
                                          height: 1.35,
                                        ),
                                      ),
                                      const SizedBox(height: 10),
                                      Text(
                                        _timeLabel(item.request.createdAt),
                                        style: TextStyle(
                                          color: Colors.white
                                              .withValues(alpha: 0.45),
                                          fontSize: 12,
                                          fontWeight: FontWeight.w500,
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      Row(
                                        children: [
                                          Expanded(
                                            child: OutlinedButton(
                                              onPressed: busy
                                                  ? null
                                                  : () => _reject(item),
                                              style: OutlinedButton.styleFrom(
                                                foregroundColor: Colors.white70,
                                                side: const BorderSide(
                                                  color: Colors.white24,
                                                ),
                                              ),
                                              child: const Text('Reject'),
                                            ),
                                          ),
                                          const SizedBox(width: 10),
                                          Expanded(
                                            child: FilledButton(
                                              onPressed: busy
                                                  ? null
                                                  : () => _approve(item),
                                              style: FilledButton.styleFrom(
                                                backgroundColor: widget.accent,
                                              ),
                                              child: busy
                                                  ? const SizedBox(
                                                      height: 18,
                                                      width: 18,
                                                      child:
                                                          CircularProgressIndicator(
                                                        strokeWidth: 2,
                                                        color: Colors.white,
                                                      ),
                                                    )
                                                  : const Text('Approve'),
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      SizedBox(
                                        width: double.infinity,
                                        child: TextButton(
                                          onPressed: busy
                                              ? null
                                              : () => widget
                                                  .onNavigateToEnvironmentApprovals(
                                                  item.environment.id,
                                                ),
                                          child: Text(
                                            'Open in Environments',
                                            style: TextStyle(
                                              color: widget.accent,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          }),
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
                          child: Row(
                            children: [
                              Text(
                                'Home insights',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleSmall
                                    ?.copyWith(
                                      color: Colors.white70,
                                      fontWeight: FontWeight.w700,
                                    ),
                              ),
                              const Spacer(),
                              TextButton(
                                onPressed: () => setState(_tips.clear),
                                style: TextButton.styleFrom(
                                  foregroundColor: widget.accent,
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 8,
                                    vertical: 4,
                                  ),
                                ),
                                child: const Text(
                                  'Clear all',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w600,
                                    fontSize: 13,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (_tips.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 20),
                            child: Text(
                              'No insight notifications',
                              style: TextStyle(
                                color: Colors.white.withValues(alpha: 0.45),
                                fontSize: 15,
                              ),
                            ),
                          )
                        else
                          ..._tips.map((n) {
                            return Padding(
                              padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
                              child: Card(
                                color: widget.cardColor,
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(14),
                                ),
                                child: Padding(
                                  padding: const EdgeInsets.all(16),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Icon(
                                            n.icon,
                                            color: widget.accent,
                                            size: 26,
                                          ),
                                          const SizedBox(width: 12),
                                          Expanded(
                                            child: Text(
                                              n.title,
                                              style: const TextStyle(
                                                color: Colors.white,
                                                fontSize: 16,
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 10),
                                      Text(
                                        n.message,
                                        style: TextStyle(
                                          color: Colors.white
                                              .withValues(alpha: 0.72),
                                          fontSize: 14,
                                          height: 1.35,
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      Align(
                                        alignment: Alignment.bottomRight,
                                        child: Text(
                                          n.timeAgo,
                                          style: TextStyle(
                                            color: Colors.white
                                                .withValues(alpha: 0.45),
                                            fontSize: 12,
                                            fontWeight: FontWeight.w500,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          }),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TipEntry {
  _TipEntry({
    required this.icon,
    required this.title,
    required this.message,
    required this.timeAgo,
  });

  final IconData icon;
  final String title;
  final String message;
  final String timeAgo;
}
