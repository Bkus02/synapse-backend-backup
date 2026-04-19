import 'package:flutter/material.dart';

import '../models/habit.dart';
import '../services/habit_api.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';

const _accent = Color(0xFF4C6FFF);
const _card = Color(0xFF0C1021);

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

  Future<void> _toggleActive(Habit h, bool value) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    setState(() => _patchingIds.add(h.id));
    try {
      final updated = await HabitApi.patch(
        habitId: h.id,
        userId: uid,
        isActive: value,
      );
      if (mounted) {
        setState(() {
          final i = _habits.indexWhere((e) => e.id == h.id);
          if (i >= 0) {
            _habits[i] = updated;
          }
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
      if (mounted) {
        setState(() => _patchingIds.remove(h.id));
      }
    }
  }

  Future<void> _confirmDelete(Habit h) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF15192E),
        title: const Text(
          'Delete habit',
          style: TextStyle(color: Colors.white),
        ),
        content: Text(
          'Remove "${h.name}"? This cannot be undone.',
          style: const TextStyle(color: Colors.white70),
        ),
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
      backgroundColor: const Color(0xFF15192E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _AddHabitSheet(
        userId: uid,
        accent: _accent,
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final uid = SessionService.instance.user?['id'] as String?;

    return Scaffold(
      backgroundColor: const Color(0xFF050814),
      floatingActionButton: uid != null
          ? FloatingActionButton.extended(
              onPressed: _loading ? null : _openAddSheet,
              backgroundColor: _accent,
              icon: const Icon(Icons.add_rounded),
              label: const Text('Add habit'),
              tooltip: 'Create a new habit',
            )
          : null,
      body: SafeArea(
        child: RefreshIndicator(
          color: _accent,
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
                      color: Colors.white,
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
                        color: Colors.white54,
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
                          color: Colors.white38,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
                  sliver: SliverList.separated(
                    itemCount: _habits.length,
                    separatorBuilder: (context, index) =>
                        const SizedBox(height: 10),
                    itemBuilder: (context, i) {
                      final h = _habits[i];
                      final busy = _patchingIds.contains(h.id);
                      return Material(
                        color: _card,
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
                                      color: _accent.withValues(alpha: 0.14),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Icon(
                                      Icons.auto_awesome,
                                      color: _accent,
                                      size: 22,
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          h.name,
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.w700,
                                            fontSize: 16,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          h.recurrence.label,
                                          style: TextStyle(
                                            color: Colors.white
                                                .withValues(alpha: 0.5),
                                            fontSize: 13,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  IconButton(
                                    onPressed: () => _confirmDelete(h),
                                    icon: const Icon(
                                      Icons.delete_outline_rounded,
                                    ),
                                    color: Colors.white38,
                                    tooltip: 'Delete',
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Text(
                                    'Active',
                                    style: theme.textTheme.labelLarge?.copyWith(
                                      color: Colors.white70,
                                    ),
                                  ),
                                  const Spacer(),
                                  if (busy)
                                    const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  else
                                    Switch.adaptive(
                                      value: h.isActive,
                                      activeTrackColor:
                                          _accent.withValues(alpha: 0.55),
                                      onChanged: (v) => _toggleActive(h, v),
                                    ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text(
                                '${(h.probabilityScore * 100).round()}%',
                                style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.38),
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
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
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _name,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              labelText: 'Name',
              labelStyle: const TextStyle(color: Colors.white54),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Colors.white24),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: widget.accent),
              ),
            ),
          ),
          const SizedBox(height: 16),
          InputDecorator(
            decoration: InputDecoration(
              labelText: 'Repeat',
              labelStyle: const TextStyle(color: Colors.white54),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Colors.white24),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: widget.accent),
              ),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<HabitRecurrence>(
                value: _recurrence,
                isExpanded: true,
                dropdownColor: const Color(0xFF1E2440),
                style: const TextStyle(color: Colors.white),
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
            title: const Text(
              'Active',
              style: TextStyle(color: Colors.white70),
            ),
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
                      color: Colors.white,
                    ),
                  )
                : const Text('Save'),
          ),
        ],
      ),
    );
  }
}
