import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _kUserJsonKey = 'synapse_current_user_json';
const _kAccessTokenKey = 'synapse_access_token';

/// Persists the signed-in user and JWT access token; dashboard, profile and
/// API clients read from here.
class SessionService extends ChangeNotifier {
  SessionService._();
  static final SessionService instance = SessionService._();

  Map<String, dynamic>? _user;
  String? _accessToken;

  Map<String, dynamic>? get user => _user;
  String? get accessToken => _accessToken;
  bool get hasToken => _accessToken != null && _accessToken!.isNotEmpty;

  /// Convenience: Authorization headers for HTTP clients.
  Map<String, String> authHeaders({Map<String, String>? base}) {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...?base,
    };
    if (hasToken) {
      headers['Authorization'] = 'Bearer $_accessToken';
    }
    return headers;
  }

  Future<void> loadFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kUserJsonKey);
    if (raw != null && raw.isNotEmpty) {
      try {
        _user = jsonDecode(raw) as Map<String, dynamic>;
      } catch (_) {
        _user = null;
      }
    } else {
      _user = null;
    }
    _accessToken = prefs.getString(_kAccessTokenKey);
    notifyListeners();
  }

  Future<void> setUser(Map<String, dynamic> user) async {
    _user = Map<String, dynamic>.from(user);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUserJsonKey, jsonEncode(_user));
    notifyListeners();
  }

  Future<void> setSession({
    required Map<String, dynamic> user,
    required String accessToken,
  }) async {
    _user = Map<String, dynamic>.from(user);
    _accessToken = accessToken;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUserJsonKey, jsonEncode(_user));
    await prefs.setString(_kAccessTokenKey, accessToken);
    notifyListeners();
  }

  Future<void> clear() async {
    _user = null;
    _accessToken = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kUserJsonKey);
    await prefs.remove(_kAccessTokenKey);
    notifyListeners();
  }
}
