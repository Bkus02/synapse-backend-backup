import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/daily_activity.dart';
import 'session_service.dart';

class UserApiException implements Exception {
  UserApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

class LoginResult {
  LoginResult({
    required this.user,
    required this.accessToken,
    required this.tokenType,
    required this.expiresIn,
  });

  final Map<String, dynamic> user;
  final String accessToken;
  final String tokenType;
  final int expiresIn;
}

class UserApi {
  UserApi._();

  /// Body matches backend `POST /users`. Parola düz metin gönderilir;
  /// backend (Sprint B) bcrypt ile hashleyip `password_hash` olarak saklar.
  static Future<Map<String, dynamic>> register({
    required String fullName,
    required String email,
    required String password,
    required int height,
    required int weight,
    required int age,
    required String location,
    required String gender,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/users');
    final body = jsonEncode(<String, dynamic>{
      'full_name': fullName,
      'email': email,
      'password': password,
      'height': height,
      'weight': weight,
      'age': age,
      'location': location,
      'gender': gender,
    });

    final response = await http.post(
      uri,
      headers: const {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: body,
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw UserApiException(_messageFromResponse(response));
  }

  static Future<LoginResult> login({
    required String email,
    required String password,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/auth/login');
    final body = jsonEncode(<String, dynamic>{
      'email': email,
      'password': password,
    });

    final response = await http.post(
      uri,
      headers: const {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: body,
    );

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      return LoginResult(
        user: Map<String, dynamic>.from(decoded['user'] as Map),
        accessToken: decoded['access_token'] as String? ?? '',
        tokenType: decoded['token_type'] as String? ?? 'bearer',
        expiresIn: (decoded['expires_in'] as num?)?.toInt() ?? 0,
      );
    }

    throw UserApiException(_messageFromResponse(response));
  }

  static Future<Map<String, dynamic>> updateUser({
    required String userId,
    required String fullName,
    required String email,
    required int height,
    required int weight,
    required int age,
    required String location,
    String? newPassword,
    String? avatarKey,
    String? gender,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/users/$userId');
    final body = <String, dynamic>{
      'full_name': fullName,
      'email': email,
      'height': height,
      'weight': weight,
      'age': age,
      'location': location,
    };
    if (avatarKey != null) {
      body['avatar_key'] = avatarKey;
    }
    if (gender != null && gender.isNotEmpty) {
      body['gender'] = gender;
    }
    if (newPassword != null && newPassword.isNotEmpty) {
      body['password'] = newPassword;
    }

    final response = await http.patch(
      uri,
      headers: SessionService.instance.authHeaders(),
      body: jsonEncode(body),
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw UserApiException(_messageFromResponse(response));
  }

  /// Returns the trailing daily activity log for the authenticated user.
  static Future<DailyActivityLog> getDailyActivity({
    required String userId,
    int days = 10,
  }) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/users/$userId/daily-activity',
    ).replace(queryParameters: {'days': days.toString()});
    final response = await http.get(
      uri,
      headers: SessionService.instance.authHeaders(),
    );
    if (response.statusCode == 200) {
      return DailyActivityLog.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(_messageFromResponse(response));
  }

  /// Shared HTTP error parsing (other API clients).
  static String errorMessageFromResponse(http.Response response) {
    return _messageFromResponse(response);
  }

  static String _messageFromResponse(http.Response response) {
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic> && decoded['detail'] != null) {
        final detail = decoded['detail'];
        if (detail is String) {
          return detail;
        }
        if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          if (first is Map && first['msg'] != null) {
            return first['msg'].toString();
          }
        }
      }
    } catch (_) {
      /* response not JSON */
    }
    return 'Server error (${response.statusCode})';
  }
}
