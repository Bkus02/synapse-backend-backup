import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';

class WeatherSnapshot {
  WeatherSnapshot({
    required this.city,
    required this.temperatureC,
    required this.condition,
    required this.summary,
    required this.tip,
    required this.isDay,
    required this.weatherCode,
  });

  final String city;
  final double temperatureC;
  final String condition;
  final String summary;
  final String tip;
  final bool isDay;
  final int weatherCode;

  factory WeatherSnapshot.fromJson(Map<String, dynamic> json) {
    return WeatherSnapshot(
      city: json['city'] as String? ?? 'istanbul',
      temperatureC: (json['temperature_c'] as num?)?.toDouble() ?? 0,
      condition: json['condition'] as String? ?? 'Mild',
      summary: json['summary'] as String? ?? '',
      tip: json['tip'] as String? ?? '',
      isDay: json['is_day'] as bool? ?? true,
      weatherCode: (json['weather_code'] as num?)?.toInt() ?? 0,
    );
  }
}

class WeatherApi {
  WeatherApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  static Future<WeatherSnapshot> current({String? city}) async {
    final query = <String, String>{};
    if (city != null && city.trim().isNotEmpty) query['city'] = city.trim();
    final uri = Uri.parse('${ApiConfig.baseUrl}/weather/current').replace(
      queryParameters: query.isEmpty ? null : query,
    );
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      return WeatherSnapshot.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
