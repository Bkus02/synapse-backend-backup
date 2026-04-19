import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _kUserJsonKey = 'synapse_current_user_json';

/// Persists the signed-in user; dashboard and profile read from here.
class SessionService extends ChangeNotifier {
  SessionService._();
  static final SessionService instance = SessionService._();

  Map<String, dynamic>? _user;

  Map<String, dynamic>? get user => _user;

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
    notifyListeners();
  }

  Future<void> setUser(Map<String, dynamic> user) async {
    _user = Map<String, dynamic>.from(user);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUserJsonKey, jsonEncode(_user));
    notifyListeners();
  }

  Future<void> clear() async {
    _user = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kUserJsonKey);
    notifyListeners();
  }
}
