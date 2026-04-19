/// Matches API `habits` + `habit_recurrence` enum.
enum HabitRecurrence {
  daily,
  weekly,
  monthly,
}

extension HabitRecurrenceX on HabitRecurrence {
  String get apiValue => switch (this) {
        HabitRecurrence.daily => 'Daily',
        HabitRecurrence.weekly => 'Weekly',
        HabitRecurrence.monthly => 'Monthly',
      };

  String get label => switch (this) {
        HabitRecurrence.daily => 'Daily',
        HabitRecurrence.weekly => 'Weekly',
        HabitRecurrence.monthly => 'Monthly',
      };
}

HabitRecurrence habitRecurrenceFromApi(String raw) {
  switch (raw) {
    case 'Daily':
      return HabitRecurrence.daily;
    case 'Weekly':
      return HabitRecurrence.weekly;
    case 'Monthly':
      return HabitRecurrence.monthly;
    default:
      return HabitRecurrence.daily;
  }
}

/// Hysteresis bands (matches DB trigger logic: above 0.6 on, below 0.45 off, between either).
enum HabitProbabilityBand {
  /// `probability_score` above 0.60 — habit is on.
  confirmed,

  /// 0.45 ≤ score ≤ 0.60 — can remain true or false until score leaves the band.
  ambiguous,

  /// `probability_score` below 0.45 — habit is off.
  notHabit,
}

extension HabitProbabilityX on Habit {
  HabitProbabilityBand get probabilityBand {
    if (probabilityScore > 0.6) {
      return HabitProbabilityBand.confirmed;
    }
    if (probabilityScore < 0.45) {
      return HabitProbabilityBand.notHabit;
    }
    return HabitProbabilityBand.ambiguous;
  }

  String get probabilityBandLabel => switch (probabilityBand) {
        HabitProbabilityBand.confirmed => 'Habit (on)',
        HabitProbabilityBand.ambiguous => 'Either on or off',
        HabitProbabilityBand.notHabit => 'Not active (off)',
      };

  String get probabilityBandDetail => switch (probabilityBand) {
        HabitProbabilityBand.confirmed =>
          'Score above 60% — counted as a habit.',
        HabitProbabilityBand.ambiguous =>
          'Between 45% and 60% — may stay true or false until the score moves out of this range.',
        HabitProbabilityBand.notHabit =>
          'Below 45% — counted as not active.',
      };
}

class Habit {
  const Habit({
    required this.id,
    required this.userId,
    required this.name,
    required this.probabilityScore,
    required this.isActive,
    required this.recurrence,
    this.deviceId,
  });

  final int id;
  final String userId;
  final String name;
  final double probabilityScore;
  final bool isActive;
  final HabitRecurrence recurrence;
  final int? deviceId;

  factory Habit.fromJson(Map<String, dynamic> json) {
    final p = json['probability_score'];
    double prob = 0.5;
    if (p is num) {
      prob = p.toDouble();
    } else if (p != null) {
      prob = double.tryParse(p.toString()) ?? 0.5;
    }
    final did = json['device_id'];
    return Habit(
      id: json['id'] as int,
      userId: json['user_id'] as String,
      name: json['name'] as String? ?? 'Habit',
      probabilityScore: prob,
      isActive: json['is_active'] as bool? ?? false,
      recurrence: habitRecurrenceFromApi(
        json['recurrence_type'] as String? ?? 'Daily',
      ),
      deviceId: did is int ? did : int.tryParse(did?.toString() ?? ''),
    );
  }
}
