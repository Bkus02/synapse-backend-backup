import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

/// Synapse FastAPI base URL (uvicorn default port 8000).
///
/// - **Android emulator:** `10.0.2.2` maps to the host machine’s localhost.
/// - **Windows / macOS / iOS simulator:** `127.0.0.1`.
/// - **Physical device:** set your PC’s LAN IP, e.g.
///   `flutter run --dart-define=API_HOST=192.168.1.10`
class ApiConfig {
  ApiConfig._();

  static const String _hostFromEnv = String.fromEnvironment('API_HOST');

  static String get baseUrl {
    if (_hostFromEnv.isNotEmpty) {
      return 'http://$_hostFromEnv:8000';
    }
    if (kIsWeb) {
      return 'http://127.0.0.1:8000';
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://127.0.0.1:8000';
  }
}
