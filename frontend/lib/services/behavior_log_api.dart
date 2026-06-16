import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';

/// Records user actions for analytics, streaks, and inference.
class BehaviorLogApi {
  BehaviorLogApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  /// Posts a behavior log. [eventTime] defaults to now (UTC).
  /// [durationMinutes] is sent as ISO-8601 duration `PT{n}M` when set.
  static Future<void> create({
    required String userId,
    required int deviceId,
    required String action,
    DateTime? eventTime,
    int? durationMinutes,
    String? parameters,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/behavior-logs');
    final when = (eventTime ?? DateTime.now()).toUtc();
    final body = <String, dynamic>{
      'user_id': userId,
      'device_id': deviceId,
      'action': action,
      'event_time': when.toIso8601String(),
      if (durationMinutes != null && durationMinutes > 0)
        'duration_hm': 'PT${durationMinutes}M',
      if (parameters != null && parameters.isNotEmpty) 'parameters': parameters,
    };
    final response = await http.post(
      uri,
      headers: _headers,
      body: jsonEncode(body),
    );
    if (response.statusCode == 200) return;
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
