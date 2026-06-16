import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';

/// JWT auth endpoints (`/auth/*`).
class AuthApi {
  AuthApi._();

  static Future<Map<String, dynamic>> fetchMe() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/auth/me');
    final response = await http.get(
      uri,
      headers: SessionService.instance.authHeaders(),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
