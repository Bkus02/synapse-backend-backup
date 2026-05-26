import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _kSelectedEnvKey = 'synapse_selected_environment_id';

/// Persists the environment shown on the dashboard (home tab).
class SelectedEnvironmentService extends ChangeNotifier {
  SelectedEnvironmentService._();
  static final SelectedEnvironmentService instance =
      SelectedEnvironmentService._();

  String? _selectedId;
  bool _loaded = false;

  String? get selectedId => _selectedId;
  bool get isLoaded => _loaded;

  Future<void> ensureLoaded() async {
    if (_loaded) return;
    final prefs = await SharedPreferences.getInstance();
    _selectedId = prefs.getString(_kSelectedEnvKey);
    _loaded = true;
    notifyListeners();
  }

  Future<void> setSelected(String environmentId) async {
    _selectedId = environmentId;
    _loaded = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kSelectedEnvKey, environmentId);
    notifyListeners();
  }

  Future<void> clear() async {
    _selectedId = null;
    _loaded = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kSelectedEnvKey);
    notifyListeners();
  }
}
