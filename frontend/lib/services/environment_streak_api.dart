import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';

class EnvironmentStreakEntry {
  EnvironmentStreakEntry({
    required this.userId,
    required this.fullName,
    required this.avatarKey,
    required this.dailyAdviceLog,
    required this.weeklyStreakCount,
  });

  final String userId;
  final String? fullName;
  final String? avatarKey;
  final List<bool> dailyAdviceLog;
  final int weeklyStreakCount;

  factory EnvironmentStreakEntry.fromJson(Map<String, dynamic> json) {
    final daysRaw = json['days'];
    final daysList = <bool>[];
    if (daysRaw is List) {
      for (final item in daysRaw) {
        if (item is bool) {
          daysList.add(item);
        } else if (item is num) {
          daysList.add(item != 0);
        } else {
          daysList.add(false);
        }
      }
    }
    return EnvironmentStreakEntry(
      userId: json['user_id'] as String? ?? '',
      fullName: json['full_name'] as String?,
      avatarKey: json['avatar_key'] as String?,
      dailyAdviceLog: daysList,
      weeklyStreakCount: (json['weekly_streak_count'] as num?)?.toInt() ?? 0,
    );
  }
}

class EnvironmentStreakApi {
  EnvironmentStreakApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  static Future<List<EnvironmentStreakEntry>> top({
    required String environmentId,
    int days = 10,
    int limit = 3,
  }) async {
    final uri =
        Uri.parse('${ApiConfig.baseUrl}/environments/$environmentId/streaks')
            .replace(queryParameters: <String, String>{
      'days': '$days',
      'limit': '$limit',
    });
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .whereType<Map<String, dynamic>>()
          .map(EnvironmentStreakEntry.fromJson)
          .toList();
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
