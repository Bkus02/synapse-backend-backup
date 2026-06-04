import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';

class AdviceCompletionLog {
  AdviceCompletionLog({
    required this.id,
    required this.userId,
    required this.adviceKey,
    required this.adviceTitle,
    required this.category,
    required this.completedAt,
    required this.durationMinutes,
  });

  final int id;
  final String userId;
  final String adviceKey;
  final String adviceTitle;
  final String category;
  final DateTime completedAt;
  final int durationMinutes;

  factory AdviceCompletionLog.fromJson(Map<String, dynamic> json) {
    return AdviceCompletionLog(
      id: (json['id'] as num?)?.toInt() ?? 0,
      userId: (json['user_id'] as String?) ?? '',
      adviceKey: (json['advice_key'] as String?) ?? '',
      adviceTitle: (json['advice_title'] as String?) ?? '',
      category: (json['category'] as String?) ?? 'Other',
      completedAt: DateTime.tryParse(json['completed_at'] as String? ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0),
      durationMinutes: (json['duration_minutes'] as num?)?.toInt() ?? 0,
    );
  }
}

class DailyStreakSnapshot {
  DailyStreakSnapshot({
    required this.currentStreak,
    required this.maxStreak,
    required this.lastQualifyingDate,
    required this.qualifyingThreshold,
    required this.completedTodayCount,
    required this.completedTodayKeys,
    required this.qualifiesToday,
  });

  final int currentStreak;
  final int maxStreak;
  final DateTime? lastQualifyingDate;
  final int qualifyingThreshold;
  final int completedTodayCount;
  final List<String> completedTodayKeys;
  final bool qualifiesToday;

  factory DailyStreakSnapshot.fromJson(Map<String, dynamic> json) {
    return DailyStreakSnapshot(
      currentStreak: (json['current_streak'] as num?)?.toInt() ?? 0,
      maxStreak: (json['max_streak'] as num?)?.toInt() ?? 0,
      lastQualifyingDate: json['last_qualifying_date'] != null
          ? DateTime.tryParse(json['last_qualifying_date'] as String)
          : null,
      qualifyingThreshold:
          (json['qualifying_threshold'] as num?)?.toInt() ?? 2,
      completedTodayCount:
          (json['completed_today_count'] as num?)?.toInt() ?? 0,
      completedTodayKeys: ((json['completed_today_keys'] as List<dynamic>?) ?? [])
          .map((e) => e.toString())
          .toList(),
      qualifiesToday: (json['qualifies_today'] as bool?) ?? false,
    );
  }
}

class PositiveAdviceApi {
  PositiveAdviceApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  static Future<AdviceCompletionLog> logCompletion({
    required String adviceKey,
    int durationMinutes = 0,
    DateTime? completedAt,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/positive-advices/logs');
    final body = <String, dynamic>{
      'advice_key': adviceKey,
      'duration_minutes': durationMinutes,
      if (completedAt != null) 'completed_at': completedAt.toUtc().toIso8601String(),
    };
    final response = await http.post(uri, headers: _headers, body: jsonEncode(body));
    if (response.statusCode == 201 || response.statusCode == 200) {
      return AdviceCompletionLog.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<List<AdviceCompletionLog>> listLogs({int limit = 100}) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/positive-advices/logs?limit=$limit');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => AdviceCompletionLog.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<DailyStreakSnapshot> getStreak() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/positive-advices/streak');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      return DailyStreakSnapshot.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
