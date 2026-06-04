import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';
import 'weather_api.dart';

class PersonalizedAdvice {
  PersonalizedAdvice({
    required this.key,
    required this.title,
    required this.summary,
    required this.iconName,
  });

  final String key;
  final String title;
  final String summary;
  final String iconName;

  factory PersonalizedAdvice.fromJson(Map<String, dynamic> json) {
    return PersonalizedAdvice(
      key: json['key'] as String? ?? '',
      title: json['title'] as String? ?? '',
      summary: json['summary'] as String? ?? '',
      iconName: json['icon'] as String? ?? 'lightbulb_outline',
    );
  }
}

class PersonalizedAdviceBundle {
  PersonalizedAdviceBundle({
    required this.advices,
    required this.city,
    required this.weather,
    required this.bmi,
    required this.bmiCategory,
    required this.ageCategory,
  });

  final List<PersonalizedAdvice> advices;
  final String city;
  final WeatherSnapshot? weather;
  final double? bmi;
  final String bmiCategory;
  final String ageCategory;

  factory PersonalizedAdviceBundle.fromJson(Map<String, dynamic> json) {
    final list = (json['advices'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(PersonalizedAdvice.fromJson)
        .toList();
    final profile = (json['profile'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final weatherJson = json['weather'];
    return PersonalizedAdviceBundle(
      advices: list,
      city: json['city'] as String? ?? 'istanbul',
      weather: weatherJson is Map<String, dynamic>
          ? WeatherSnapshot.fromJson(weatherJson)
          : null,
      bmi: (profile['bmi'] as num?)?.toDouble(),
      bmiCategory: profile['bmi_category'] as String? ?? 'normal',
      ageCategory: profile['age_category'] as String? ?? 'adult',
    );
  }
}

class PersonalizedAdviceApi {
  PersonalizedAdviceApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  static Future<PersonalizedAdviceBundle> fetch(String userId) async {
    final uri =
        Uri.parse('${ApiConfig.baseUrl}/users/$userId/personalized-advices');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      return PersonalizedAdviceBundle.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
