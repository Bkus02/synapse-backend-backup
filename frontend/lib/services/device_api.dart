import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/environment_device.dart';
import 'user_api.dart';

class DeviceApi {
  DeviceApi._();

  static const _headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  static Future<List<EnvironmentDevice>> listForEnvironment({
    required String environmentId,
    required String userId,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/devices').replace(
      queryParameters: <String, String>{
        'environment_id': environmentId,
        'user_id': userId,
      },
    );
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => EnvironmentDevice.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<EnvironmentDevice> create({
    required String userId,
    required String environmentId,
    required EnvironmentDeviceType type,
    required String name,
    String? room,
    bool status = false,
    double? currentValue,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/devices').replace(
      queryParameters: <String, String>{'user_id': userId},
    );
    final body = <String, dynamic>{
      'environment_id': environmentId,
      'type': type.apiValue,
      'name': name.trim().isEmpty ? 'Device' : name.trim(),
      'status': status,
      if (room != null && room.trim().isNotEmpty) 'room': room.trim(),
      'current_value': ?currentValue,
    };
    final response = await http.post(
      uri,
      headers: _headers,
      body: jsonEncode(body),
    );
    if (response.statusCode == 200) {
      return EnvironmentDevice.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> delete({
    required int deviceId,
    required String userId,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/devices/$deviceId').replace(
      queryParameters: <String, String>{'user_id': userId},
    );
    final response = await http.delete(uri, headers: _headers);
    if (response.statusCode == 200) {
      return;
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }
}
