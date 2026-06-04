import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../models/advice_detail_data.dart';
import '../models/daily_activity.dart';
import '../models/environment_summary.dart';
import '../models/habit.dart';
import '../models/recommendation.dart' as api;
import '../services/environment_api.dart';
import '../services/environment_streak_api.dart';
import '../services/habit_api.dart';
import '../services/join_request_inbox.dart';
import '../services/notification_api.dart';
import '../services/personalized_advice_api.dart';
import '../services/recommendation_api.dart';
import '../services/selected_environment_service.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';
import '../services/weather_api.dart';
import '../utils/material_icon_lookup.dart';
import '../widgets/istanbul_clock.dart';
import '../widgets/notifications_modal.dart';
import '../widgets/profile_modal.dart';
import '../widgets/streak_gene_widget.dart';
import 'environments_page.dart';
import 'habits_page.dart';

const _kAdviceItems = [
  AdviceDetailData(
    title: 'Reading Time',
    summary:
        'Wind down with a focused session; Synapse aligns lighting with your routine.',
    icon: Icons.menu_book,
    adviceKey: 'reading_time',
  ),
  AdviceDetailData(
    title: 'Fruit Break',
    summary:
        'Add one portion of fruit to your evening routine for a steady energy curve.',
    icon: Icons.restaurant_rounded,
    adviceKey: 'fruit_break',
  ),
  AdviceDetailData(
    title: 'Light Walk',
    summary:
        'Short movement breaks help circulation; your home can support the habit.',
    icon: Icons.directions_walk,
    adviceKey: 'light_walk',
  ),
];

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  int _selectedIndex = 0;
  String? _pendingOpenEnvironmentId;
  int _notificationBadgeCount = 0;

  @override
  void initState() {
    super.initState();
    SessionService.instance.addListener(_onSessionChanged);
    _refreshNotificationBadge();
  }

  @override
  void dispose() {
    SessionService.instance.removeListener(_onSessionChanged);
    super.dispose();
  }

  void _onSessionChanged() {
    _refreshNotificationBadge();
  }

  Future<void> _refreshNotificationBadge() async {
    var count = 0;
    try {
      count += await JoinRequestInbox.pendingCountForAdmin();
      if (SessionService.instance.hasToken) {
        count += await NotificationApi.badge();
      }
    } catch (_) {
      // Badge is best-effort; ignore transient API errors.
    }
    if (mounted) {
      setState(() => _notificationBadgeCount = count);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synapse'),
        actions: [
          const IstanbulClock(),
          Stack(
            clipBehavior: Clip.none,
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_none_outlined),
                onPressed: () {
                  NotificationsModal.show(
                    context,
                    onNavigateToEnvironmentApprovals: (environmentId) {
                      setState(() {
                        _pendingOpenEnvironmentId = environmentId;
                        _selectedIndex = 1;
                      });
                    },
                    onSheetClosed: _refreshNotificationBadge,
                  );
                },
              ),
              if (_notificationBadgeCount > 0)
                Positioned(
                  right: 10,
                  top: 10,
                  child: IgnorePointer(
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: Color(0xFFFF5252),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                ),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.account_circle_outlined),
            onPressed: () => ProfileModal.show(context),
          ),
        ],
      ),
      body: IndexedStack(
        index: _selectedIndex,
        children: [
          const MainPage(),
          EnvironmentsPage(
            pendingOpenEnvironmentId: _pendingOpenEnvironmentId,
            onPendingOpenConsumed: () {
              setState(() => _pendingOpenEnvironmentId = null);
            },
          ),
          const HabitsPage(),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        backgroundColor: AppColors.surface,
        selectedItemColor: AppColors.accent,
        unselectedItemColor: AppColors.textSecondary,
        currentIndex: _selectedIndex,
        onTap: (index) {
          setState(() => _selectedIndex = index);
          if (index == 1) {
            _refreshNotificationBadge();
          }
        },
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home),
            label: 'Main',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.domain),
            label: 'Environments',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.auto_awesome),
            label: 'Habits',
          ),
        ],
      ),
    );
  }
}

class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  static const _daysToShow = 10;

  final List<_FamilyMemberProgress> _family = [];
  List<EnvironmentSummary> _environments = [];
  String? _selectedEnvironmentId;
  String? _selectedEnvironmentName;
  String? _loadError;
  bool _loadingFamily = true;

  List<Habit> _activeHabits = const [];

  api.Recommendation? _activeRecommendation;
  bool _loadingRecommendation = false;
  bool _actingOnRecommendation = false;
  Timer? _recommendationPoll;

  int _geneProgressStep = 0;

  PersonalizedAdviceBundle? _adviceBundle;
  bool _loadingAdvices = false;

  @override
  void initState() {
    super.initState();
    SessionService.instance.addListener(_onSessionChanged);
    SelectedEnvironmentService.instance.addListener(_onEnvironmentSelection);
    _loadEnvironmentFamily();
    _pollRecommendation();
    _loadPersonalizedAdvices();
    _recommendationPoll = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _pollRecommendation(),
    );
  }

  Future<void> _loadPersonalizedAdvices() async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null || !SessionService.instance.hasToken) {
      if (mounted) setState(() => _adviceBundle = null);
      return;
    }
    if (mounted) setState(() => _loadingAdvices = true);
    try {
      final bundle = await PersonalizedAdviceApi.fetch(uid);
      if (mounted) {
        setState(() {
          _adviceBundle = bundle;
          _loadingAdvices = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingAdvices = false);
    }
  }

  @override
  void dispose() {
    _recommendationPoll?.cancel();
    SessionService.instance.removeListener(_onSessionChanged);
    SelectedEnvironmentService.instance.removeListener(_onEnvironmentSelection);
    super.dispose();
  }

  void _onSessionChanged() {
    if (mounted) {
      _loadEnvironmentFamily();
      _pollRecommendation();
      _loadPersonalizedAdvices();
    }
  }

  void _onEnvironmentSelection() {
    if (mounted) {
      _loadEnvironmentFamily();
    }
  }

  Future<void> _pollRecommendation() async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null || !SessionService.instance.hasToken) {
      if (mounted) {
        setState(() {
          _activeRecommendation = null;
          _loadingRecommendation = false;
        });
      }
      return;
    }
    if (mounted) setState(() => _loadingRecommendation = true);
    try {
      final rec = await RecommendationApi.getActive(userId: uid);
      if (mounted) {
        setState(() {
          _activeRecommendation = rec;
          _loadingRecommendation = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingRecommendation = false);
    }
  }

  Future<void> _respondToRecommendation(bool accept) async {
    final rec = _activeRecommendation;
    if (rec == null || _actingOnRecommendation) return;
    setState(() => _actingOnRecommendation = true);
    try {
      if (accept) {
        await RecommendationApi.accept(rec.id);
      } else {
        await RecommendationApi.reject(rec.id);
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(accept ? 'Suggestion accepted' : 'Suggestion dismissed'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        setState(() => _activeRecommendation = null);
        await _pollRecommendation();
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
      if (mounted) setState(() => _actingOnRecommendation = false);
    }
  }

  Future<void> _loadEnvironmentFamily() async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) {
      setState(() {
        _family.clear();
        _environments = [];
        _selectedEnvironmentId = null;
        _selectedEnvironmentName = null;
        _loadError = null;
        _loadingFamily = false;
      });
      return;
    }

    setState(() {
      _loadingFamily = true;
      _loadError = null;
    });

    try {
      await SelectedEnvironmentService.instance.ensureLoaded();
      final envs = await EnvironmentApi.listForUser(uid);
      if (envs.isEmpty) {
        if (mounted) {
          setState(() {
            _environments = [];
            _family.clear();
            _selectedEnvironmentId = null;
            _selectedEnvironmentName = null;
            _loadingFamily = false;
          });
        }
        return;
      }

      var envId = SelectedEnvironmentService.instance.selectedId;
      if (envId == null || !envs.any((e) => e.id == envId)) {
        envId = envs.first.id;
        await SelectedEnvironmentService.instance.setSelected(envId);
      }
      final env = envs.firstWhere((e) => e.id == envId);
      final myId = uid;

      List<EnvironmentStreakEntry> topStreaks = const [];
      try {
        topStreaks = await EnvironmentStreakApi.top(
          environmentId: envId,
          days: _daysToShow,
          limit: 3,
        );
      } catch (_) {
        // Streak feed is best-effort; fall back to members API below.
      }

      DailyActivityLog? myActivity;
      try {
        myActivity = await UserApi.getDailyActivity(
          userId: myId,
          days: _daysToShow,
        );
      } catch (_) {
        // Activity log is best-effort; fall back to placeholder zeros.
      }

      List<Habit> habits = const [];
      try {
        final all = await HabitApi.listForUser(myId);
        habits = all.where((h) => h.isActive).toList();
      } catch (_) {
        // Habits feed is best-effort; fall back to the static advice list.
      }

      final family = <_FamilyMemberProgress>[];
      if (topStreaks.isNotEmpty) {
        for (final entry in topStreaks) {
          final name = entry.fullName?.trim().isNotEmpty == true
              ? entry.fullName!.trim()
              : entry.userId;
          final isMe = entry.userId == myId;
          final flags = entry.dailyAdviceLog.isEmpty
              ? List<bool>.filled(_daysToShow, false)
              : entry.dailyAdviceLog;
          family.add(
            _FamilyMemberProgress(
              userId: entry.userId,
              name: name,
              environmentId: envId,
              dailyAdviceLog: List<bool>.of(flags),
              isCurrentUser: isMe,
            ),
          );
        }
      } else {
        // Fallback: best-effort members fetch when streaks endpoint fails.
        final members = await EnvironmentApi.listMembers(envId);
        for (final m in members) {
          final name = m.fullName?.trim().isNotEmpty == true
              ? m.fullName!.trim()
              : m.userId;
          final isMe = m.userId == myId;
          family.add(
            _FamilyMemberProgress(
              userId: m.userId,
              name: name,
              environmentId: envId,
              dailyAdviceLog: isMe && myActivity != null
                  ? myActivity.activeFlags
                  : List<bool>.filled(_daysToShow, false),
              isCurrentUser: isMe,
            ),
          );
        }
        if (family.length > 3) {
          family.removeRange(3, family.length);
        }
      }

      if (mounted) {
        setState(() {
          _environments = envs;
          _selectedEnvironmentId = envId;
          _selectedEnvironmentName = env.name;
          _family
            ..clear()
            ..addAll(family);
          _activeHabits = habits;
          _geneProgressStep = myActivity?.weeklyStreakCount ?? 0;
          _loadingFamily = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loadError = e.toString();
          _loadingFamily = false;
        });
      }
    }
  }

  Future<void> _pickEnvironment() async {
    if (_environments.length < 2) return;
    final picked = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppColors.surface,
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Select home environment',
                  style: TextStyle(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                  ),
                ),
              ),
              ..._environments.map((env) {
                return ListTile(
                  title: Text(
                    env.name,
                    style: const TextStyle(color: AppColors.textPrimary),
                  ),
                  subtitle: Text(
                    env.id,
                    style: const TextStyle(color: AppColors.textSecondary),
                  ),
                  trailing: env.id == _selectedEnvironmentId
                      ? const Icon(Icons.check_rounded, color: AppColors.accent)
                      : null,
                  onTap: () => Navigator.pop(ctx, env.id),
                );
              }),
            ],
          ),
        );
      },
    );
    if (picked != null && picked != _selectedEnvironmentId) {
      await SelectedEnvironmentService.instance.setSelected(picked);
    }
  }

  _FamilyMemberProgress? get _currentUser {
    for (final member in _family) {
      if (member.isCurrentUser) return member;
    }
    return null;
  }

  /// Build inline cards for the user's own positive habits (Custom + Advice-promoted).
  ///
  /// Rendered directly inside the "Active Advices" list — there is no separate
  /// "Your Habits" panel. Device routine/sequence habits are filtered out
  /// (they live in the Habits page under "Device Habits").
  List<Widget> _buildMyPositiveHabits() {
    if (_activeHabits.isEmpty) return const [];
    final mine = _activeHabits
        .where((h) => h.kind == HabitKind.positive)
        .toList()
      ..sort((a, b) => b.probabilityScore.compareTo(a.probabilityScore));
    if (mine.isEmpty) return const [];

    return mine.map((h) => _MyHabitTile(habit: h)).toList();
  }

  Future<void> _openAdviceEntryDialog(AdviceDetailData advice) async {
    final durationController = TextEditingController();
    TimeOfDay? startTime;

    await showDialog<void>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setInnerState) {
            return AlertDialog(
              backgroundColor: AppColors.surface,
              title: Text(
                '${advice.title} - Hour/Minute',
                style: const TextStyle(color: AppColors.textPrimary),
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Start time',
                    style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () async {
                        final picked = await showTimePicker(
                          context: context,
                          initialTime: startTime ?? TimeOfDay.now(),
                        );
                        if (picked != null) {
                          setInnerState(() => startTime = picked);
                        }
                      },
                      icon: const Icon(Icons.schedule_rounded),
                      label: Text(
                        startTime == null
                            ? 'Select'
                            : '${startTime!.hour.toString().padLeft(2, '0')}:${startTime!.minute.toString().padLeft(2, '0')}',
                      ),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: durationController,
                    keyboardType: TextInputType.number,
                    style: const TextStyle(color: AppColors.textPrimary),
                    decoration: const InputDecoration(
                      labelText: 'Duration (minute)',
                      labelStyle: TextStyle(color: AppColors.textSecondary),
                      enabledBorder: UnderlineInputBorder(
                        borderSide: BorderSide(color: AppColors.borderStrong),
                      ),
                      focusedBorder: UnderlineInputBorder(
                        borderSide: BorderSide(color: AppColors.accent),
                      ),
                    ),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () async {
                    final minutes = int.tryParse(durationController.text.trim());
                    if (startTime == null || minutes == null || minutes <= 0) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text(
                            'Please select a start time and a valid duration.',
                          ),
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                      return;
                    }
                    final key = advice.adviceKey;
                    if (key == null || key.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text(
                            'This advice is not linked to a backend key yet.',
                          ),
                          backgroundColor: Colors.redAccent,
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                      return;
                    }
                    final now = DateTime.now();
                    final localStart = DateTime(
                      now.year,
                      now.month,
                      now.day,
                      startTime!.hour,
                      startTime!.minute,
                    );
                    Navigator.of(ctx).pop();
                    try {
                      await NotificationApi.scheduleAdvice(
                        adviceKey: key,
                        scheduledFor: localStart,
                        durationMinutes: minutes,
                      );
                      if (!mounted) return;
                      final hh = startTime!.hour.toString().padLeft(2, '0');
                      final mm = startTime!.minute.toString().padLeft(2, '0');
                      ScaffoldMessenger.of(this.context).showSnackBar(
                        SnackBar(
                          content: Text(
                            'Reminder set: ${advice.title} at $hh:$mm '
                            '($minutes min). Confirm from the bell when ready.',
                          ),
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                    } on UserApiException catch (e) {
                      if (!mounted) return;
                      ScaffoldMessenger.of(this.context).showSnackBar(
                        SnackBar(
                          content: Text(e.message),
                          backgroundColor: Colors.redAccent,
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                    }
                  },
                  child: const Text('Save'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final me = _currentUser;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _TopSection(
              theme: theme,
              me: me,
              weather: _adviceBundle?.weather,
              city: _adviceBundle?.city,
            ),
            const SizedBox(height: 12),
            Expanded(
              child: ListView(
                children: [
                  if (_selectedEnvironmentName != null) ...[
                    InkWell(
                      onTap: _environments.length > 1 ? _pickEnvironment : null,
                      borderRadius: BorderRadius.circular(12),
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Row(
                          children: [
                            const Icon(
                              Icons.home_work_outlined,
                              color: Color(0xFF8EA2FF),
                              size: 20,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                _selectedEnvironmentName!,
                                style: theme.textTheme.titleSmall?.copyWith(
                                  color: AppColors.textSecondary,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                            if (_environments.length > 1)
                              const Icon(
                                Icons.unfold_more_rounded,
                                color: AppColors.textSecondary,
                                size: 20,
                              ),
                          ],
                        ),
                      ),
                    ),
                  ],
                  if (_loadError != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        _loadError!,
                        style: const TextStyle(
                          color: Colors.redAccent,
                          fontSize: 12,
                        ),
                      ),
                    ),
                  if (_activeRecommendation != null) ...[
                    _RecommendationBanner(
                      recommendation: _activeRecommendation!,
                      busy: _actingOnRecommendation,
                      onAccept: () => _respondToRecommendation(true),
                      onReject: () => _respondToRecommendation(false),
                    ),
                    const SizedBox(height: 12),
                  ] else if (_loadingRecommendation &&
                      SessionService.instance.hasToken)
                    const Padding(
                      padding: EdgeInsets.only(bottom: 12),
                      child: LinearProgressIndicator(minHeight: 2),
                    ),
                  Text(
                    'Community Progress',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: AppColors.textPrimary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 10),
                  _CommunityProgressCard(
                    loading: _loadingFamily,
                    family: _family,
                    emptyHint: _environments.isEmpty
                        ? 'Create or join an environment to see your household.'
                        : 'No members in this environment yet.',
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'Active Advices',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: AppColors.textPrimary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (me != null) ...[
                    StreakGeneWidget(
                      days: me.dailyAdviceLog,
                      progressionStep: _geneProgressStep,
                    ),
                    const SizedBox(height: 12),
                  ],
                  if (_adviceBundle != null &&
                      _adviceBundle!.advices.isNotEmpty)
                    ..._adviceBundle!.advices.map((a) {
                      final detail = AdviceDetailData(
                        title: a.title,
                        summary: a.summary,
                        icon: iconForName(a.iconName),
                        adviceKey: a.key,
                      );
                      return _AdviceTile(
                        data: detail,
                        onTap: () => _openAdviceEntryDialog(detail),
                      );
                    })
                  else if (_loadingAdvices)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Center(
                        child: SizedBox(
                          height: 24,
                          width: 24,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      ),
                    )
                  else
                    ..._kAdviceItems.map(
                      (advice) => _AdviceTile(
                        data: advice,
                        onTap: () => _openAdviceEntryDialog(advice),
                      ),
                    ),
                  // User's own positive habits (manual "Add Habit" entries +
                  // advice-promoted habits). Adherence percent is shown
                  // inline. Device routine/sequence habits are filtered out.
                  ..._buildMyPositiveHabits(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TopSection extends StatelessWidget {
  const _TopSection({
    required this.theme,
    required this.me,
    required this.weather,
    required this.city,
  });

  final ThemeData theme;
  final _FamilyMemberProgress? me;
  final WeatherSnapshot? weather;
  final String? city;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _WeatherCard(theme: theme, weather: weather, city: city),
        const SizedBox(height: 10),
        Text(
          'Welcome back,',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: AppColors.textSecondary,
          ),
        ),
        Text(
          me?.name ?? 'Guest',
          style: theme.textTheme.headlineSmall?.copyWith(
            color: AppColors.textPrimary,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _RecommendationBanner extends StatelessWidget {
  const _RecommendationBanner({
    required this.recommendation,
    required this.busy,
    required this.onAccept,
    required this.onReject,
  });

  final api.Recommendation recommendation;
  final bool busy;
  final VoidCallback onAccept;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.auto_awesome, color: AppColors.accent, size: 20),
              SizedBox(width: 8),
              Text(
                'Synapse suggestion',
                style: TextStyle(
                  color: AppColors.textPrimary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            recommendation.headline,
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            recommendation.body,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              height: 1.35,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: busy ? null : onReject,
                  child: const Text('Dismiss'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton(
                  onPressed: busy ? null : onAccept,
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.accent,
                  ),
                  child: busy
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: AppColors.textOnAccent,
                          ),
                        )
                      : const Text('Accept'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CommunityProgressCard extends StatelessWidget {
  const _CommunityProgressCard({
    required this.loading,
    required this.family,
    this.emptyHint = 'Environment Family not found.',
  });

  final bool loading;
  final List<_FamilyMemberProgress> family;
  final String emptyHint;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (loading) {
      return const _CardContainer(
        child: SizedBox(
          height: 72,
          child: Center(
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }

    if (family.isEmpty) {
      return _CardContainer(
        child: Text(
          emptyHint,
          style: const TextStyle(color: AppColors.textSecondary),
        ),
      );
    }

    var maxWeekly = 0;
    for (final m in family) {
      if (m.weeklyStreakCount > maxWeekly) {
        maxWeekly = m.weeklyStreakCount;
      }
    }

    return _CardContainer(
      child: Column(
        children: family.map((member) {
          final isLeader = member.weeklyStreakCount == maxWeekly && maxWeekly > 0;
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            member.name,
                            style: theme.textTheme.titleSmall?.copyWith(
                              color: AppColors.textPrimary,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          if (isLeader) ...[
                            const SizedBox(width: 6),
                            const Text('👑'),
                          ],
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '🔥 ${member.weeklyStreakCount}',
                        style: const TextStyle(
                          color: Color(0xFF8EA2FF),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                SizedBox(
                  width: 122,
                  height: 52,
                  child: StreakGeneWidget(
                    days: member.dailyAdviceLog,
                    compact: true,
                    progressionStep: member.weeklyStreakCount,
                  ),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _WeatherCard extends StatelessWidget {
  const _WeatherCard({
    required this.theme,
    required this.weather,
    required this.city,
  });

  final ThemeData theme;
  final WeatherSnapshot? weather;
  final String? city;

  IconData get _conditionIcon {
    final w = weather;
    if (w == null) return Icons.wb_sunny_rounded;
    if (!w.isDay) return Icons.nightlight_round;
    switch (w.condition) {
      case 'Clear':
        return Icons.wb_sunny_rounded;
      case 'Partly cloudy':
        return Icons.wb_cloudy_rounded;
      case 'Cloudy':
        return Icons.cloud_rounded;
      case 'Fog':
        return Icons.foggy;
      case 'Drizzle':
      case 'Rain':
      case 'Rain showers':
        return Icons.umbrella_rounded;
      case 'Snow':
      case 'Snow showers':
        return Icons.ac_unit_rounded;
      case 'Thunderstorm':
        return Icons.thunderstorm_rounded;
      case 'Freezing rain':
        return Icons.severe_cold_rounded;
      default:
        return Icons.wb_sunny_rounded;
    }
  }

  List<Color> get _conditionGradient {
    final w = weather;
    if (w == null) {
      return [const Color(0xFFFFD54F), const Color(0xFFFFB300)];
    }
    switch (w.condition) {
      case 'Clear':
        return [const Color(0xFFFFD54F), const Color(0xFFFFB300)];
      case 'Partly cloudy':
        return [const Color(0xFFB0BEC5), const Color(0xFF78909C)];
      case 'Cloudy':
      case 'Fog':
        return [const Color(0xFF90A4AE), const Color(0xFF546E7A)];
      case 'Drizzle':
      case 'Rain':
      case 'Rain showers':
        return [const Color(0xFF64B5F6), const Color(0xFF1976D2)];
      case 'Snow':
      case 'Snow showers':
      case 'Freezing rain':
        return [const Color(0xFFE1F5FE), const Color(0xFF90CAF9)];
      case 'Thunderstorm':
        return [const Color(0xFF7E57C2), const Color(0xFF311B92)];
      default:
        return [const Color(0xFFFFD54F), const Color(0xFFFFB300)];
    }
  }

  @override
  Widget build(BuildContext context) {
    final w = weather;
    final cityLabel = (city ?? 'istanbul');
    final cityNice = cityLabel.isEmpty
        ? 'Istanbul'
        : '${cityLabel[0].toUpperCase()}${cityLabel.substring(1)}';
    final headline = w == null
        ? 'Loading weather…'
        : '${w.temperatureC.toStringAsFixed(0)}°C • ${w.condition}';
    final subtitle = w?.tip ?? 'Tap to refresh after sign-in.';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
        boxShadow: AppColors.cardShadow,
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(colors: _conditionGradient),
            ),
            child: Icon(
              _conditionIcon,
              color: AppColors.textOnAccent,
              size: 26,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      cityNice,
                      style: theme.textTheme.labelMedium?.copyWith(
                        color: AppColors.textSecondary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (w != null) ...[
                      const SizedBox(width: 6),
                      Container(
                        width: 4,
                        height: 4,
                        decoration: const BoxDecoration(
                          color: AppColors.textSecondary,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        w.isDay ? 'Day' : 'Night',
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: AppColors.textSecondary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  headline,
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CardContainer extends StatelessWidget {
  final Widget child;

  const _CardContainer({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
      ),
      child: child,
    );
  }
}

class _AdviceTile extends StatelessWidget {
  final AdviceDetailData data;
  final VoidCallback onTap;

  const _AdviceTile({
    required this.data,
    required this.onTap,
  });

  static const _accent = AppColors.accent;
  static const _card = AppColors.surface;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.border),
          color: _card,
        ),
        clipBehavior: Clip.antiAlias,
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            splashColor: _accent.withValues(alpha: 0.12),
            highlightColor: _accent.withValues(alpha: 0.06),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: _accent.withValues(alpha: 0.16),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(
                          data.icon,
                          color: _accent,
                          size: 22,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          data.title,
                          style: const TextStyle(
                            color: AppColors.textPrimary,
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                          ),
                        ),
                      ),
                      Icon(
                        Icons.schedule_rounded,
                        color: AppColors.textSecondary,
                        size: 20,
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    data.summary,
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 13,
                      height: 1.35,
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

/// Compact dashboard card for the user's own positive habits.
///
/// Shows: prefix-trimmed name, "Manuel"/"Tavsiye" badge, recurrence label,
/// adherence percentage bar (from `probability_score`), and a colored band
/// reflecting the hysteresis state (confirmed / ambiguous / not active).
class _MyHabitTile extends StatelessWidget {
  const _MyHabitTile({required this.habit});

  final Habit habit;

  @override
  Widget build(BuildContext context) {
    final pct = (habit.probabilityScore.clamp(0.0, 1.0) * 100).round();
    final band = habit.probabilityBand;
    final Color barColor = switch (band) {
      HabitProbabilityBand.confirmed => Colors.greenAccent.shade700,
      HabitProbabilityBand.ambiguous => Colors.orangeAccent,
      HabitProbabilityBand.notHabit => Colors.redAccent,
    };
    final String stateLabel = switch (band) {
      HabitProbabilityBand.confirmed => 'Habit formed',
      HabitProbabilityBand.ambiguous => 'On track — keep it consistent',
      HabitProbabilityBand.notHabit => 'Not a habit yet',
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.border),
        ),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: AppColors.accent.withValues(alpha: 0.16),
                      borderRadius: BorderRadius.circular(11),
                    ),
                    child: const Icon(
                      Icons.auto_awesome_rounded,
                      color: AppColors.accent,
                      size: 20,
                    ),
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
                                habit.displayName,
                                style: const TextStyle(
                                  color: AppColors.textPrimary,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 15,
                                ),
                              ),
                            ),
                            const SizedBox(width: 6),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 7, vertical: 2),
                              decoration: BoxDecoration(
                                color: AppColors.surfaceMuted,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                habit.kindBadge,
                                style: const TextStyle(
                                  color: AppColors.textSecondary,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: 0.3,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 2),
                        Text(
                          habit.recurrence.label,
                          style: const TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 12,
                          ),
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
                ],
              ),
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: habit.probabilityScore.clamp(0.0, 1.0),
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
}


class _FamilyMemberProgress {
  _FamilyMemberProgress({
    required this.userId,
    required this.name,
    required this.environmentId,
    required this.dailyAdviceLog,
    this.isCurrentUser = false,
  });

  final String userId;
  final String name;
  final String environmentId;
  final bool isCurrentUser;
  final List<bool> dailyAdviceLog;

  int get weeklyStreakCount {
    final from = dailyAdviceLog.length >= 7 ? dailyAdviceLog.length - 7 : 0;
    var total = 0;
    for (var i = from; i < dailyAdviceLog.length; i++) {
      if (dailyAdviceLog[i]) total += 1;
    }
    return total;
  }
}
