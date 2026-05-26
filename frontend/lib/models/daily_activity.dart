class DailyActivityDay {
  const DailyActivityDay({required this.date, required this.active});

  final String date;
  final bool active;

  factory DailyActivityDay.fromJson(Map<String, dynamic> json) {
    return DailyActivityDay(
      date: json['date'] as String,
      active: json['active'] as bool,
    );
  }
}

class DailyActivityLog {
  const DailyActivityLog({
    required this.userId,
    required this.days,
    required this.weeklyStreakCount,
  });

  final String userId;
  final List<DailyActivityDay> days;
  final int weeklyStreakCount;

  List<bool> get activeFlags => days.map((d) => d.active).toList();

  factory DailyActivityLog.fromJson(Map<String, dynamic> json) {
    final list = (json['days'] as List<dynamic>? ?? const []);
    return DailyActivityLog(
      userId: json['user_id'] as String,
      days: list
          .map((e) => DailyActivityDay.fromJson(e as Map<String, dynamic>))
          .toList(),
      weeklyStreakCount: (json['weekly_streak_count'] as num?)?.toInt() ?? 0,
    );
  }
}
