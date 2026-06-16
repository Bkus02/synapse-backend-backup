import 'package:flutter/material.dart';

import 'services/auth_api.dart';
import 'services/recommendation_refresh_service.dart';
import 'services/selected_environment_service.dart';
import 'services/session_service.dart';
import 'services/user_api.dart';
import 'screens/welcome_screen.dart';
import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'theme/app_theme.dart';
import 'widgets/auth_gate.dart';

Future<String> _resolveInitialRoute() async {
  if (!SessionService.instance.hasToken) {
    return '/welcome';
  }
  try {
    final me = await AuthApi.fetchMe();
    await SessionService.instance.setUser(me);
    return '/dashboard';
  } on UserApiException {
    await SessionService.instance.clear();
  } catch (_) {
    await SessionService.instance.clear();
  }
  return '/welcome';
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SessionService.instance.loadFromPrefs();
  await SelectedEnvironmentService.instance.ensureLoaded();
  RecommendationRefreshService.instance.attach();
  final initialRoute = await _resolveInitialRoute();
  runApp(SynapseApp(initialRoute: initialRoute));
}

class SynapseApp extends StatelessWidget {
  const SynapseApp({super.key, required this.initialRoute});

  final String initialRoute;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Synapse',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      initialRoute: initialRoute,
      routes: {
        '/welcome': (_) => const WelcomePage(),
        '/login': (context) {
          final args = ModalRoute.of(context)?.settings.arguments;
          String? prefillEmail;
          String? initialSnack;
          if (args is String) {
            prefillEmail = args;
          } else if (args is Map) {
            prefillEmail = args['email'] as String?;
            initialSnack = args['snack'] as String?;
          }
          return LoginPage(
            prefillEmail: prefillEmail,
            initialSnack: initialSnack,
          );
        },
        '/dashboard': (_) => const AuthGate(child: DashboardPage()),
      },
    );
  }
}

