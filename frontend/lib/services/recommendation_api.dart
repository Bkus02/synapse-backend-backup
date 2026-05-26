import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/recommendation.dart';
import 'session_service.dart';
import 'user_api.dart';

class RecommendationApi {
  RecommendationApi._();

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  static Future<Recommendation?> getActive({required String userId}) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/recommendations/active')
        .replace(queryParameters: <String, String>{'user_id': userId});
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      if (response.body.trim().isEmpty || response.body.trim() == 'null') {
        return null;
      }
      final decoded = jsonDecode(response.body);
      if (decoded == null) return null;
      return Recommendation.fromJson(decoded as Map<String, dynamic>);
    }
    if (response.statusCode == 401) {
      throw UserApiException('Sign in required to load recommendations.');
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> accept(String recommendationId) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/recommendations/$recommendationId/accept',
    );
    final response = await http.post(uri, headers: _headers);
    if (response.statusCode == 200) return;
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> reject(String recommendationId) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/recommendations/$recommendationId/reject',
    );
    final response = await http.post(uri, headers: _headers);
    if (response.statusCode == 200) return;
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
