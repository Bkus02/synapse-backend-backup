import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'session_service.dart';
import 'user_api.dart';

class TuyaLampStatus {
  TuyaLampStatus({
    required this.deviceId,
    required this.name,
    required this.online,
    required this.isOn,
    required this.brightnessPercent,
  });

  final String deviceId;
  final String name;
  final bool online;
  final bool? isOn;
  final int? brightnessPercent;

  factory TuyaLampStatus.fromJson(Map<String, dynamic> json) {
    final info = (json['info'] as Map?)?.cast<String, dynamic>() ?? const {};
    final parsed =
        (json['parsed'] as Map?)?.cast<String, dynamic>() ?? const {};
    return TuyaLampStatus(
      deviceId: (json['device_id'] as String?) ?? '',
      name: (info['name'] as String?) ??
          (parsed['name'] as String?) ??
          'Smart Life lamp',
      online: (parsed['online'] as bool?) ?? (info['online'] as bool?) ?? false,
      isOn: parsed['is_on'] as bool?,
      brightnessPercent: (parsed['brightness_percent'] as num?)?.toInt(),
    );
  }
}

class TuyaLampApi {
  TuyaLampApi._();

  static const _base = '/integrations/tuya/lamp';

  static Map<String, String> get _headers =>
      SessionService.instance.authHeaders();

  static Future<bool> isConfigured() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}$_base/configured');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode != 200) return false;
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['configured'] as bool? ?? false;
  }

  static Future<TuyaLampStatus> status() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}$_base/status');
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      return TuyaLampStatus.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw UserApiException(UserApi.errorMessageFromResponse(response));
  }

  static Future<void> turnOn() => _command('on');
  static Future<void> turnOff() => _command('off');

  static Future<void> setBrightness(int percent) async {
    final clamped = percent.clamp(0, 100);
    final uri = Uri.parse('${ApiConfig.baseUrl}$_base/brightness');
    final response = await http.post(
      uri,
      headers: {..._headers, 'Content-Type': 'application/json'},
      body: jsonEncode({'value': clamped}),
    );
    if (response.statusCode != 200) {
      throw UserApiException(UserApi.errorMessageFromResponse(response));
    }
  }

  static Future<void> _command(String op) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}$_base/$op');
    final response = await http.post(uri, headers: _headers);
    if (response.statusCode != 200) {
      throw UserApiException(UserApi.errorMessageFromResponse(response));
    }
  }
}
