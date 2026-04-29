import 'package:flutter/material.dart';

import '../models/advice_detail_data.dart';
import '../services/join_request_inbox.dart';
import '../services/session_service.dart';
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
  ),
  AdviceDetailData(
    title: 'Fruit Break',
    summary:
        'Add one portion of fruit to your evening routine for a steady energy curve.',
    icon: Icons.restaurant_rounded,
  ),
  AdviceDetailData(
    title: 'Light Walk',
    summary:
        'Short movement breaks help circulation; your home can support the habit.',
    icon: Icons.directions_walk,
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
  int _joinRequestBadgeCount = 0;

  @override
  void initState() {
    super.initState();
    SessionService.instance.addListener(_onSessionChanged);
    _refreshJoinBadge();
  }

  @override
  void dispose() {
    SessionService.instance.removeListener(_onSessionChanged);
    super.dispose();
  }

  void _onSessionChanged() {
    _refreshJoinBadge();
  }

  Future<void> _refreshJoinBadge() async {
    final n = await JoinRequestInbox.pendingCountForAdmin();
    if (mounted) {
      setState(() => _joinRequestBadgeCount = n);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synapse'),
        actions: [
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
                    onSheetClosed: _refreshJoinBadge,
                  );
                },
              ),
              if (_joinRequestBadgeCount > 0)
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
        backgroundColor: const Color(0xFF050814),
        selectedItemColor: const Color(0xFF4C6FFF),
        unselectedItemColor: Colors.white54,
        currentIndex: _selectedIndex,
        onTap: (index) {
          setState(() => _selectedIndex = index);
          if (index == 1) {
            _refreshJoinBadge();
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
  static const _homeEnvironmentId = 'env-demo-01';
  static const _daysToShow = 10;

  final List<_FamilyMemberProgress> _family = [];
  bool _loadingFamily = true;

  int _geneProgressStep = 0;
  DateTime? _lastMarkedDate;

  @override
  void initState() {
    super.initState();
    SessionService.instance.addListener(_onSessionChanged);
    _loadEnvironmentFamily();
  }

  @override
  void dispose() {
    SessionService.instance.removeListener(_onSessionChanged);
    super.dispose();
  }

  void _onSessionChanged() {
    if (mounted) {
      _loadEnvironmentFamily();
    }
  }

  Future<void> _loadEnvironmentFamily() async {
    // Placeholder for querying `user_environments` by `environment_id`.
    await Future<void>.delayed(const Duration(milliseconds: 200));

    final u = SessionService.instance.user;
    final myName = u?['full_name'] as String? ?? 'Guest';
    final myId = u?['id'] as String? ?? 'me-001';

    final seed = <_FamilyMemberProgress>[
      _FamilyMemberProgress(
        userId: myId,
        name: myName,
        environmentId: _homeEnvironmentId,
        dailyAdviceLog: [false, true, true, false, true, true, true, false, true, false],
        isCurrentUser: true,
      ),
      _FamilyMemberProgress(
        userId: 'friend-101',
        name: 'Berkay',
        environmentId: _homeEnvironmentId,
        dailyAdviceLog: [true, true, false, true, true, true, true, true, false, true],
      ),
      _FamilyMemberProgress(
        userId: 'friend-102',
        name: 'Ece',
        environmentId: _homeEnvironmentId,
        dailyAdviceLog: [false, true, false, true, false, false, true, true, false, false],
      ),
    ];

    setState(() {
      _family
        ..clear()
        ..addAll(seed.where((e) => e.environmentId == _homeEnvironmentId));
      _loadingFamily = false;
    });
  }

  _FamilyMemberProgress? get _currentUser {
    for (final member in _family) {
      if (member.isCurrentUser) return member;
    }
    return null;
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
              backgroundColor: const Color(0xFF151A2E),
              title: Text(
                '${advice.title} - Hour/Minute',
                style: const TextStyle(color: Colors.white),
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Start time',
                    style: TextStyle(color: Colors.white70, fontSize: 13),
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
                    style: const TextStyle(color: Colors.white),
                    decoration: const InputDecoration(
                      labelText: 'Duration (minute)',
                      labelStyle: TextStyle(color: Colors.white70),
                      enabledBorder: UnderlineInputBorder(
                        borderSide: BorderSide(color: Colors.white30),
                      ),
                      focusedBorder: UnderlineInputBorder(
                        borderSide: BorderSide(color: Color(0xFF4C6FFF)),
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
                  onPressed: () {
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
                    Navigator.of(ctx).pop();
                    _markAdviceCompletedToday();
                    ScaffoldMessenger.of(this.context).showSnackBar(
                      SnackBar(
                        content: Text(
                          'Saved for ${advice.title}: ${startTime!.hour.toString().padLeft(2, '0')}:${startTime!.minute.toString().padLeft(2, '0')} - $minutes min',
                        ),
                        behavior: SnackBarBehavior.floating,
                      ),
                    );
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

  void _markAdviceCompletedToday() {
    final me = _currentUser;
    if (me == null) return;

    final now = DateTime.now();
    final sameDay = _lastMarkedDate != null &&
        _lastMarkedDate!.year == now.year &&
        _lastMarkedDate!.month == now.month &&
        _lastMarkedDate!.day == now.day;

    setState(() {
      if (me.dailyAdviceLog.length >= _daysToShow) {
        me.dailyAdviceLog.removeAt(0);
      }
      me.dailyAdviceLog.add(true);
      if (!sameDay) {
        _geneProgressStep += 1;
      }
      _lastMarkedDate = now;
    });
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
            _TopSection(theme: theme, me: me),
            const SizedBox(height: 12),
            Expanded(
              child: ListView(
                children: [
                  Text(
                    'Community Progress',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 10),
                  _CommunityProgressCard(
                    loading: _loadingFamily,
                    family: _family,
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'Active Advices',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: Colors.white,
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
                  ..._kAdviceItems.map(
                    (advice) => _AdviceTile(
                      data: advice,
                      onTap: () => _openAdviceEntryDialog(advice),
                    ),
                  ),
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
  });

  final ThemeData theme;
  final _FamilyMemberProgress? me;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _WeatherCard(theme: theme),
        const SizedBox(height: 10),
        Text(
          'Welcome back,',
          style: theme.textTheme.bodyMedium?.copyWith(color: Colors.white70),
        ),
        Text(
          me?.name ?? 'Guest',
          style: theme.textTheme.headlineSmall?.copyWith(
            color: Colors.white,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _CommunityProgressCard extends StatelessWidget {
  const _CommunityProgressCard({
    required this.loading,
    required this.family,
  });

  final bool loading;
  final List<_FamilyMemberProgress> family;

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
      return const _CardContainer(
        child: Text(
          'Environment Family not found.',
          style: TextStyle(color: Colors.white70),
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
                              color: Colors.white,
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
  final ThemeData theme;

  const _WeatherCard({required this.theme});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0C1021),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.4),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
        border: Border.all(color: Colors.white10),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                colors: [
                  Color(0xFFFFD54F),
                  Color(0xFFFFB300),
                ],
              ),
            ),
            child: const Icon(
              Icons.wb_sunny_rounded,
              color: Colors.white,
              size: 26,
            ),
          ),
          const SizedBox(width: 16),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '24°C - Sunny',
                style: theme.textTheme.titleMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Perfect conditions for natural light.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: Colors.white70,
                ),
              ),
            ],
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
        color: const Color(0xFF0C1021),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white10),
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

  static const _accent = Color(0xFF4C6FFF);
  static const _card = Color(0xFF0C1021);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white10),
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
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                          ),
                        ),
                      ),
                      Icon(
                        Icons.schedule_rounded,
                        color: Colors.white.withValues(alpha: 0.55),
                        size: 20,
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    data.summary,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.72),
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
