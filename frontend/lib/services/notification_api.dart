import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';

/// One row in the bell-modal feed (mirrors `app/api/routes/notifications.py`).
class AppNotification {
  AppNotification({
    required this.id,
    required this.userId,
    required this.kind,
    required this.title,
    required this.body,
    required this.scheduledFor,
    required this.firedAt,
    required this.status,
    required this.requiresAction,
    required this.payload,
  });

  final int id;
  final String userId;
  final String kind;
  final String title;
  final String body;
  final DateTime? scheduledFor;
  final DateTime? firedAt;
  final String status;
  final bool requiresAction;
  final Map<String, dynamic> payload;

  bool get isFired => status == 'fired';
  bool get isPending => status == 'pending';
  bool get isClosed => status == 'confirmed' || status == 'dismissed';

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    DateTime? parse(String? s) {
      if (s == null || s.isEmpty) return null;
      return DateTime.tryParse(s);
    }

    return AppNotification(
      id: (json['id'] as num).toInt(),
      userId: (json['user_id'] as String?) ?? '',
      kind: (json['kind'] as String?) ?? 'unknown',
      title: (json['title'] as String?) ?? '',
      body: (json['body'] as String?) ?? '',
      scheduledFor: parse(json['scheduled_for'] as String?),
      firedAt: parse(json['fired_at'] as String?),
      status: (json['status'] as String?) ?? 'pending',
      requiresAction: (json['requires_action'] as bool?) ?? false,
      payload: ((json['payload'] as Map?) ?? const {})
          .map((k, v) => MapEntry(k.toString(), v)),
    );
  }
}

class NotificationApi {
  NotificationApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  /// Fetch the bell-modal feed for the signed-in user. Server-side this also
  /// flips any due `pending` rows to `fired` first.
  static Future<List<AppNotification>> feed({
    bool includeExpired = false,
    int limit = 50,
  }) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/notifications'
      '?include_expired=$includeExpired&limit=$limit',
    );
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => AppNotification.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<int> badge() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/notifications/badge');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return (json['unread'] as num?)?.toInt() ?? 0;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<AppNotification> confirm(int id) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/notifications/$id/confirm');
    final response = await http.post(uri, headers: _headers);
    if (response.statusCode == 200) {
      return AppNotification.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<AppNotification> dismiss(int id) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/notifications/$id/dismiss');
    final response = await http.post(uri, headers: _headers);
    if (response.statusCode == 200) {
      return AppNotification.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  /// Demo helper: re-run all of today's generators ("treat today as day 31").
  /// No auth required on the server beyond the standard middleware (it is
  /// idempotent and only writes for users that already exist in the DB).
  static Future<Map<String, int>> seedToday() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/notifications/seed-today');
    final response = await http.post(uri, headers: _headers);
    if (response.statusCode == 200) {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return json.map((k, v) => MapEntry(k, (v as num).toInt()));
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  /// Create a planned advice session ("I'll run at 18:00 for 30 min").
  /// The backend also drops a paired `advice_reminder` notification.
  static Future<Map<String, dynamic>> scheduleAdvice({
    required String adviceKey,
    required DateTime scheduledFor,
    int durationMinutes = 0,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/advice-schedules');
    final body = jsonEncode({
      'advice_key': adviceKey,
      'scheduled_for': scheduledFor.toUtc().toIso8601String(),
      'duration_minutes': durationMinutes,
    });
    final response = await http.post(uri, headers: _headers, body: body);
    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
