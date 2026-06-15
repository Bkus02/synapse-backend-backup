import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/environment_member.dart';
import '../models/environment_summary.dart';
import '../models/join_request.dart';
import 'session_service.dart';
import 'user_api.dart';

class EnvironmentApi {
  EnvironmentApi._();

  static Future<String> suggestEnvironmentId() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/environments/suggest-id');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final map = jsonDecode(response.body) as Map<String, dynamic>;
      return map['id'] as String;
    }
    throw UserApiException('Could not load suggested ID (${response.statusCode})');
  }

  static Future<List<EnvironmentSummary>> listForUser(String userId) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/environments/for-user/$userId',
    );
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => EnvironmentSummary.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw UserApiException('Could not load environments (${response.statusCode})');
  }

  static Future<EnvironmentSummary> create({
    required String id,
    required String name,
    required String location,
    required String adminId,
    required String iconKey,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/environments');
    final body = jsonEncode(<String, dynamic>{
      'id': id,
      'name': name,
      'location': location,
      'admin_id': adminId,
      'icon_key': iconKey,
    });
    final response = await http.post(uri, headers: _headers, body: body);
    if (response.statusCode == 200) {
      return EnvironmentSummary.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> requestJoin({
    required String environmentId,
    required String userId,
  }) async {
    final uri =
        Uri.parse('${ApiConfig.baseUrl}/environments/$environmentId/join-requests');
    final body = jsonEncode(<String, dynamic>{'user_id': userId});
    final response = await http.post(uri, headers: _headers, body: body);
    if (response.statusCode == 200) {
      return;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<List<JoinRequest>> listJoinRequests({
    required String environmentId,
    required String adminUserId,
  }) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/environments/$environmentId/join-requests',
    );
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => JoinRequest.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    if (response.statusCode == 403) {
      return [];
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> approveJoinRequest({
    required String environmentId,
    required int requestId,
    required String adminUserId,
  }) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/environments/$environmentId/join-requests/$requestId/approve',
    );
    final body = jsonEncode(<String, dynamic>{'admin_user_id': adminUserId});
    final response = await http.post(uri, headers: _headers, body: body);
    if (response.statusCode == 200) {
      return;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> rejectJoinRequest({
    required String environmentId,
    required int requestId,
    required String adminUserId,
  }) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/environments/$environmentId/join-requests/$requestId/reject',
    );
    final body = jsonEncode(<String, dynamic>{'admin_user_id': adminUserId});
    final response = await http.post(uri, headers: _headers, body: body);
    if (response.statusCode == 200) {
      return;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<List<EnvironmentMember>> listMembers(String environmentId) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/environments/$environmentId/members',
    );
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => EnvironmentMember.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw UserApiException('Could not load members (${response.statusCode})');
  }

  static Future<void> removeMember({
    required String environmentId,
    required String userId,
  }) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/environments/$environmentId/members/$userId',
    );
    final response = await http.delete(uri, headers: _headers);
    if (response.statusCode == 200) {
      return;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();
}
