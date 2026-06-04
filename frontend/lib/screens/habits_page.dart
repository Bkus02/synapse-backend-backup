import 'package:flutter/material.dart';

import '../models/habit.dart';
import '../services/habit_api.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';
import '../theme/app_colors.dart';

class HabitsPage extends StatefulWidget {
  const HabitsPage({super.key});

  @override
  State<HabitsPage> createState() => _HabitsPageState();
}

class _HabitsPageState extends State<HabitsPage> {
  List<Habit> _habits = [];
  bool _loading = true;
  String? _error;
  final Set<int> _patchingIds = {};

  @override
  void initState() {
    super.initState();
    SessionService.instance.addListener(_onSession);
    _load();
  }

  @override
  void dispose() {
    SessionService.instance.removeListener(_onSession);
    super.dispose();
  }

  void _onSession() {
    if (mounted) {
      _load();
    }
  }

  Future<void> _load() async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) {
      setState(() {
        _habits = [];
        _loading = false;
        _error = null;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await HabitApi.listForUser(uid);
      if (mounted) {
        setState(() {
          _habits = list;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  Future<void> _confirmDelete(Habit h) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete habit'),
        content: Text('Remove "${h.name}"? This cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: Colors.redAccent),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await HabitApi.delete(habitId: h.id, userId: uid);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Habit deleted'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        _load();
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
    }
  }

  void _openAddSheet() {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Sign in to manage habits.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _AddHabitSheet(
        userId: uid,
        accent: AppColors.accent,
        onCreated: () {
          Navigator.pop(ctx);
          _load();
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Habit created'),
              behavior: SnackBarBehavior.floating,
            ),
          );
        },
      ),
    );
  }

  List<Widget> _buildHabitSections(ThemeData theme) {
    final device = _habits.where((h) => h.kind == HabitKind.device).toList();
    final positive =
        _habits.where((h) => h.kind == HabitKind.positive).toList();

    int byProb(Habit a, Habit b) => b.probabilityScore.compareTo(a.probabilityScore);
    device.sort(byProb);
    positive.sort(byProb);

    final sections = <Widget>[];
    if (positive.isNotEmpty) {
      sections.add(_sectionHeader(
        theme,
        title: 'Positive Habits',
        subtitle: 'Advice + manually-added habits',
        icon: Icons.favorite_rounded,
        count: positive.length,
      ));
      sections.add(_habitListSliver(positive, theme));
    }
    if (device.isNotEmpty) {
      sections.add(_sectionHeader(
        theme,
        title: 'Device Habits',
        subtitle: 'Auto-discovered device routines from logs',
        icon: Icons.devices_rounded,
        count: device.length,
      ));
      sections.add(_habitListSliver(device, theme));
    }
    sections.add(const SliverToBoxAdapter(child: SizedBox(height: 100)));
    return sections;
  }

  Widget _sectionHeader(
    ThemeData theme, {
    required String title,
    required String subtitle,
    required IconData icon,
    required int count,
  }) {
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 8),
      sliver: SliverToBoxAdapter(
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppColors.accentLight,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: AppColors.accent, size: 18),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: AppColors.textPrimary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  Text(
                    subtitle,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border),
              ),
              child: Text(
                '$count',
                style: TextStyle(
                  color: AppColors.textPrimary,
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _habitListSliver(List<Habit> habits, ThemeData theme) {
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      sliver: SliverList.separated(
        itemCount: habits.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (context, i) => _habitCard(habits[i], theme),
      ),
    );
  }

  Widget _habitCard(Habit h, ThemeData theme) {
    final busy = _patchingIds.contains(h.id);
    final isDevice = h.kind == HabitKind.device;
    final iconData = isDevice ? Icons.devices_rounded : Icons.auto_awesome;

    final pct = (h.probabilityScore.clamp(0.0, 1.0) * 100).round();
    final band = h.probabilityBand;
    final barColor = switch (band) {
      HabitProbabilityBand.confirmed => Colors.greenAccent.shade700,
      HabitProbabilityBand.ambiguous => Colors.orangeAccent,
      HabitProbabilityBand.notHabit => Colors.redAccent,
    };
    final stateLabel = switch (band) {
      HabitProbabilityBand.confirmed => 'Habit formed',
      HabitProbabilityBand.ambiguous => 'On track — keep going',
      HabitProbabilityBand.notHabit => 'Not a habit yet',
    };

    return Container(
      decoration: AppColors.cardDecoration(),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(16),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AppColors.accentLight,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(iconData, color: AppColors.accent, size: 22),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                h.displayName,
                                style: const TextStyle(
                                  color: AppColors.textPrimary,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 16,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.surface,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: AppColors.border),
                              ),
                              child: Text(
                                h.kindBadge,
                                style: TextStyle(
                                  color: AppColors.textSecondary,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            Text(
                              h.recurrence.label,
                              style: TextStyle(
                                color: AppColors.textSecondary,
                                fontSize: 13,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              width: 4,
                              height: 4,
                              decoration: BoxDecoration(
                                color: AppColors.textMuted,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              h.isActive ? 'Active' : 'Inactive',
                              style: TextStyle(
                                color: h.isActive
                                    ? Colors.greenAccent.shade700
                                    : AppColors.textMuted,
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '$pct%',
                    style: TextStyle(
                      color: barColor,
                      fontWeight: FontWeight.w800,
                      fontSize: 16,
                    ),
                  ),
                  IconButton(
                    onPressed: busy ? null : () => _confirmDelete(h),
                    icon: busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child:
                                CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.delete_outline_rounded),
                    color: AppColors.textMuted,
                    tooltip: 'Delete',
                  ),
                ],
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: h.probabilityScore.clamp(0.0, 1.0),
                  minHeight: 6,
                  backgroundColor: AppColors.surfaceMuted,
                  valueColor: AlwaysStoppedAnimation<Color>(barColor),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                stateLabel,
                style: const TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final uid = SessionService.instance.user?['id'] as String?;

    return Scaffold(
      floatingActionButton: uid != null
          ? FloatingActionButton.extended(
              onPressed: _loading ? null : _openAddSheet,
              backgroundColor: AppColors.accent,
              icon: const Icon(Icons.add_rounded),
              label: const Text('Add habit'),
              tooltip: 'Create a new habit',
            )
          : null,
      body: SafeArea(
        child: RefreshIndicator(
          color: AppColors.accent,
          onRefresh: _load,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
                sliver: SliverToBoxAdapter(
                  child: Text(
                    'Habits',
                    style: theme.textTheme.titleLarge?.copyWith(
                      color: AppColors.textPrimary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              if (_loading)
                const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: CircularProgressIndicator()),
                  ),
                )
              else if (uid == null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      'Sign in to load your habits.',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
                )
              else if (_error != null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      _error!,
                      style: const TextStyle(color: Colors.redAccent),
                    ),
                  ),
                )
              else if (_habits.isEmpty)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Text(
                        'No habits yet.\nTap Add habit to create one.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodyLarge?.copyWith(
                          color: AppColors.textMuted,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ),
                )
              else
                ..._buildHabitSections(theme),
            ],
          ),
        ),
      ),
    );
  }
}

class _AddHabitSheet extends StatefulWidget {
  const _AddHabitSheet({
    required this.userId,
    required this.accent,
    required this.onCreated,
  });

  final String userId;
  final Color accent;
  final VoidCallback onCreated;

  @override
  State<_AddHabitSheet> createState() => _AddHabitSheetState();
}

class _AddHabitSheetState extends State<_AddHabitSheet> {
  final _name = TextEditingController();
  HabitRecurrence _recurrence = HabitRecurrence.daily;
  bool _isActive = true;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Enter a name'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      await HabitApi.create(
        userId: widget.userId,
        name: _name.text,
        recurrence: _recurrence,
        isActive: _isActive,
        probabilityScore: 0.5,
      );
      if (mounted) {
        widget.onCreated();
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
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    const types = [
      HabitRecurrence.daily,
      HabitRecurrence.weekly,
      HabitRecurrence.monthly,
    ];
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'New habit',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      color: AppColors.textOnAccent,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Name'),
          ),
          const SizedBox(height: 16),
          InputDecorator(
            decoration: const InputDecoration(labelText: 'Repeat'),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<HabitRecurrence>(
                value: _recurrence,
                isExpanded: true,
                dropdownColor: AppColors.surface,
                items: types
                    .map(
                      (t) => DropdownMenuItem(
                        value: t,
                        child: Text(t.label),
                      ),
                    )
                    .toList(),
                onChanged: _saving
                    ? null
                    : (v) {
                        if (v != null) {
                          setState(() => _recurrence = v);
                        }
                      },
              ),
            ),
          ),
          const SizedBox(height: 12),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: const Text('Active'),
            value: _isActive,
            activeTrackColor: widget.accent.withValues(alpha: 0.55),
            onChanged: _saving
                ? null
                : (v) {
                    setState(() => _isActive = v);
                  },
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _saving ? null : _submit,
            style: FilledButton.styleFrom(
              backgroundColor: widget.accent,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: _saving
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.textPrimary,
                    ),
                  )
                : const Text('Save'),
          ),
        ],
      ),
    );
  }
}
