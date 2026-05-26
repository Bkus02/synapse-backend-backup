import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/habit.dart';
import 'session_service.dart';
import 'user_api.dart';

class HabitApi {
  HabitApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  static Future<List<Habit>> listForUser(String userId) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/habits');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => Habit.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<Habit> create({
    required String userId,
    required String name,
    required HabitRecurrence recurrence,
    bool isActive = true,
    double probabilityScore = 0.5,
    int? deviceId,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/habits');
    final body = <String, dynamic>{
      'user_id': userId,
      'name': name.trim().isEmpty ? 'Habit' : name.trim(),
      'probability_score': probabilityScore,
      'is_active': isActive,
      'recurrence_type': recurrence.apiValue,
      'device_id': ?deviceId,
    };
    final response = await http.post(
      uri,
      headers: _headers,
      body: jsonEncode(body),
    );
    if (response.statusCode == 200) {
      return Habit.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<Habit> patch({
    required int habitId,
    required String userId,
    String? name,
    bool? isActive,
    HabitRecurrence? recurrence,
    double? probabilityScore,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/habits/$habitId');
    final body = <String, dynamic>{
      'name': ?name,
      'is_active': ?isActive,
      'recurrence_type': ?(recurrence?.apiValue),
      'probability_score': ?probabilityScore,
    };
    final response = await http.patch(
      uri,
      headers: _headers,
      body: jsonEncode(body),
    );
    if (response.statusCode == 200) {
      return Habit.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> delete({
    required int habitId,
    String? userId,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/habits/$habitId');
    final response = await http.delete(uri, headers: _headers);
    if (response.statusCode == 200) {
      return;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
