import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../services/environment_api.dart';
import '../services/join_request_inbox.dart';
import '../services/notification_api.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';

/// In-app notifications: the persistent backend feed (morning greeting,
/// device routine confirms, advice reminders, streak milestones, sequence
/// triggers) PLUS real environment join requests with Approve / Reject.
class NotificationsModal {
  NotificationsModal._();

  static Future<void> show(
    BuildContext context, {
    required void Function(String environmentId) onNavigateToEnvironmentApprovals,
    VoidCallback? onSheetClosed,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: AppColors.modalBarrier,
      builder: (sheetContext) {
        return _NotificationsSheet(
          sheetColor: AppColors.surface,
          cardColor: AppColors.surfaceMuted,
          accent: AppColors.accent,
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
  static String _timeLabel(DateTime? dt) {
    if (dt == null) return 'Pending';
    final local = dt.toLocal();
    final diff = DateTime.now().difference(local);
    if (diff.isNegative) {
      final hh = local.hour.toString().padLeft(2, '0');
      final mm = local.minute.toString().padLeft(2, '0');
      return 'at $hh:$mm';
    }
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inHours < 1) return '${diff.inMinutes} min ago';
    if (diff.inDays < 1) return '${diff.inHours} hr ago';
    if (diff.inDays < 7) return '${diff.inDays} d ago';
    return '${(diff.inDays / 7).floor()} wk ago';
  }

  // Real backend feed.
  List<AppNotification> _notifications = [];
  bool _loadingFeed = true;
  String? _feedError;
  final Set<int> _busyNotificationIds = {};

  // Join requests (unchanged).
  List<JoinRequestInboxItem> _joinItems = [];
  bool _loadingJoin = true;
  String? _joinError;
  final Set<int> _busyJoinIds = {};

  @override
  void initState() {
    super.initState();
    _loadFeed();
    _loadJoin();
  }

  // ---------------------------------------------------------------- feed

  Future<void> _loadFeed() async {
    if (!SessionService.instance.hasToken) {
      if (mounted) {
        setState(() {
          _notifications = [];
          _loadingFeed = false;
        });
      }
      return;
    }
    setState(() {
      _loadingFeed = true;
      _feedError = null;
    });
    try {
      // Auto-generate today's notifications (idempotent) so reminders arrive
      // without any manual action.
      try {
        await NotificationApi.seedToday();
      } catch (_) {
        // Best-effort: still show whatever feed already exists.
      }
      final feed = await NotificationApi.feed(limit: 60);
      if (mounted) {
        setState(() {
          _notifications = feed;
          _loadingFeed = false;
        });
      }
    } on UserApiException catch (e) {
      if (mounted) {
        setState(() {
          _feedError = e.message;
          _loadingFeed = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _feedError = e.toString();
          _loadingFeed = false;
        });
      }
    }
  }

  Future<void> _confirmNotification(AppNotification n) async {
    if (_busyNotificationIds.contains(n.id)) return;
    setState(() => _busyNotificationIds.add(n.id));
    try {
      final updated = await NotificationApi.confirm(n.id);
      if (mounted) {
        setState(() {
          _notifications = _notifications
              .map((item) => item.id == updated.id ? updated : item)
              .toList();
        });
        SessionService.instance.notifyActivityChanged();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Confirmed: ${n.title}'),
            behavior: SnackBarBehavior.floating,
          ),
        );
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
      if (mounted) setState(() => _busyNotificationIds.remove(n.id));
    }
  }

  Future<void> _dismissNotification(AppNotification n) async {
    if (_busyNotificationIds.contains(n.id)) return;
    setState(() => _busyNotificationIds.add(n.id));
    try {
      final updated = await NotificationApi.dismiss(n.id);
      if (mounted) {
        setState(() {
          _notifications = _notifications
              .map((item) => item.id == updated.id ? updated : item)
              .toList();
        });
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
      if (mounted) setState(() => _busyNotificationIds.remove(n.id));
    }
  }

  // ----------------------------------------------------------- join requests

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

  Future<void> _approveJoin(JoinRequestInboxItem item) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    setState(() => _busyJoinIds.add(item.request.id));
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
      if (mounted) setState(() => _busyJoinIds.remove(item.request.id));
    }
  }

  Future<void> _rejectJoin(JoinRequestInboxItem item) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    setState(() => _busyJoinIds.add(item.request.id));
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
      if (mounted) setState(() => _busyJoinIds.remove(item.request.id));
    }
  }

  // -------------------------------------------------------------- helpers

  IconData _iconForKind(String kind) {
    switch (kind) {
      case 'morning_greeting':
        return Icons.wb_sunny_rounded;
      case 'advice_reminder':
        return Icons.directions_run_rounded;
      case 'device_routine':
        return Icons.tune_rounded;
      case 'sequence_trigger':
        return Icons.bolt_rounded;
      case 'streak_milestone':
        return Icons.local_fire_department_rounded;
      case 'streak_risk':
        return Icons.whatshot_rounded;
      case 'safety_anomaly':
        return Icons.warning_amber_rounded;
      default:
        return Icons.notifications_rounded;
    }
  }

  Color _accentForKind(String kind) {
    if (kind == 'safety_anomaly') {
      return const Color(0xFFFF5252);
    }
    return widget.accent;
  }

  String _sectionHeaderForKind(String kind) {
    switch (kind) {
      case 'safety_anomaly':
        return 'Safety alerts';
      case 'morning_greeting':
        return 'Daily';
      case 'advice_reminder':
      case 'streak_risk':
        return 'Positive advice';
      case 'device_routine':
      case 'sequence_trigger':
        return 'Device habits';
      case 'streak_milestone':
        return 'Milestones';
      default:
        return 'Other';
    }
  }

  String _confirmLabelForKind(String kind) {
    switch (kind) {
      case 'advice_reminder':
        return "I'm starting";
      case 'device_routine':
      case 'sequence_trigger':
        return 'Confirm';
      default:
        return 'OK';
    }
  }

  String _dismissLabelForKind(String kind) {
    switch (kind) {
      case 'advice_reminder':
        return 'Skip';
      default:
        return 'Not now';
    }
  }

  // ---------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final sheetHeight = media.size.height * 0.87;

    final visible = _notifications
        .where((n) => n.status != 'expired')
        .toList();

    // Group by section header
    final grouped = <String, List<AppNotification>>{};
    for (final n in visible) {
      grouped
          .putIfAbsent(_sectionHeaderForKind(n.kind), () => [])
          .add(n);
    }
    const sectionOrder = [
      'Safety alerts',
      'Daily',
      'Positive advice',
      'Device habits',
      'Milestones',
      'Other',
    ];

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
                            color: AppColors.textPrimary.withValues(alpha: 0.28),
                            borderRadius: BorderRadius.circular(999),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Text(
                            'Notifications',
                            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                  color: AppColors.textPrimary,
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                        ),
                        IconButton(
                          onPressed: () {
                            _loadFeed();
                            _loadJoin();
                          },
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
                        if (_loadingFeed)
                          const Padding(
                            padding: EdgeInsets.all(20),
                            child: Center(
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                          )
                        else if (_feedError != null)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                            child: Text(
                              _feedError!,
                              style: const TextStyle(
                                color: Colors.redAccent,
                                fontSize: 13,
                              ),
                            ),
                          )
                        else if (visible.isEmpty)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                            child: Text(
                              SessionService.instance.user == null
                                  ? 'Sign in to see your notifications.'
                                  : 'Nothing for today yet.',
                              style: TextStyle(
                                color: AppColors.textPrimary.withValues(alpha: 0.45),
                                fontSize: 14,
                              ),
                            ),
                          )
                        else
                          ...sectionOrder
                              .where((s) => grouped[s] != null)
                              .expand((s) sync* {
                            yield Padding(
                              padding: const EdgeInsets.fromLTRB(20, 8, 20, 6),
                              child: Text(
                                s,
                                style: Theme.of(context)
                                    .textTheme
                                    .titleSmall
                                    ?.copyWith(
                                      color: AppColors.textSecondary,
                                      fontWeight: FontWeight.w700,
                                    ),
                              ),
                            );
                            for (final n in grouped[s]!) {
                              yield _notificationCard(n);
                            }
                          }),
                        const SizedBox(height: 14),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 20),
                          child: Text(
                            'Join requests',
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(
                                  color: AppColors.textSecondary,
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
                                color: AppColors.textPrimary.withValues(alpha: 0.45),
                                fontSize: 14,
                              ),
                            ),
                          )
                        else
                          ..._joinItems.map(_joinCard),
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

  Widget _notificationCard(AppNotification n) {
    final busy = _busyNotificationIds.contains(n.id);
    final closed = n.isClosed;
    final closedHint = n.status == 'confirmed'
        ? 'Confirmed'
        : (n.status == 'dismissed' ? 'Dismissed' : null);
    final cardAccent = _accentForKind(n.kind);
    final isAlert = n.kind == 'safety_anomaly';
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
      child: Card(
        color: widget.cardColor,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: isAlert
              ? BorderSide(color: cardAccent.withValues(alpha: 0.75), width: 1.4)
              : BorderSide.none,
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(_iconForKind(n.kind), color: cardAccent, size: 26),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      n.title,
                      style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                n.body,
                style: TextStyle(
                  color: AppColors.textPrimary.withValues(alpha: 0.72),
                  fontSize: 14,
                  height: 1.35,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Text(
                    _timeLabel(n.firedAt ?? n.scheduledFor),
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  if (closedHint != null) ...[
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.surface.withValues(alpha: 0.45),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                        closedHint,
                        style: const TextStyle(
                          color: AppColors.textSecondary,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
              if (n.requiresAction && !closed) ...[
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: busy ? null : () => _dismissNotification(n),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.textSecondary,
                          side: const BorderSide(color: AppColors.border),
                        ),
                        child: Text(_dismissLabelForKind(n.kind)),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: FilledButton(
                        onPressed: busy ? null : () => _confirmNotification(n),
                        style: FilledButton.styleFrom(
                          backgroundColor: widget.accent,
                        ),
                        child: busy
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: AppColors.textPrimary,
                                ),
                              )
                            : Text(_confirmLabelForKind(n.kind)),
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _joinCard(JoinRequestInboxItem item) {
    final busy = _busyJoinIds.contains(item.request.id);
    final who = (item.request.requesterName?.trim().isNotEmpty ?? false)
        ? item.request.requesterName!.trim()
        : item.request.userId;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
      child: Card(
        color: widget.cardColor,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
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
                        color: AppColors.textPrimary,
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
                  color: AppColors.textPrimary.withValues(alpha: 0.72),
                  fontSize: 14,
                  height: 1.35,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                _timeLabel(DateTime.tryParse(item.request.createdAt ?? '')),
                style: const TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: busy ? null : () => _rejectJoin(item),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.textSecondary,
                        side: const BorderSide(color: AppColors.border),
                      ),
                      child: const Text('Reject'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: FilledButton(
                      onPressed: busy ? null : () => _approveJoin(item),
                      style: FilledButton.styleFrom(
                        backgroundColor: widget.accent,
                      ),
                      child: busy
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppColors.textPrimary,
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
                      : () => widget.onNavigateToEnvironmentApprovals(
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
  }
}
