import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';

class UserApiException implements Exception {
  UserApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

class UserApi {
  UserApi._();

  /// Body matches backend `POST /users`. `password_hash` is sent as plain text
  /// for now; production should hash passwords on the server.
  static Future<Map<String, dynamic>> register({
    required String fullName,
    required String email,
    required String password,
    required int height,
    required int weight,
    required int age,
    required String location,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/users');
    final body = jsonEncode(<String, dynamic>{
      'full_name': fullName,
      'email': email,
      'password_hash': password,
      'height': height,
      'weight': weight,
      'age': age,
      'location': location,
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

  static Future<Map<String, dynamic>> login({
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
      return jsonDecode(response.body) as Map<String, dynamic>;
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
    if (newPassword != null && newPassword.isNotEmpty) {
      body['password_hash'] = newPassword;
    }

    final response = await http.patch(
      uri,
      headers: const {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode(body),
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
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
