import 'package:flutter/material.dart';

import 'services/selected_environment_service.dart';
import 'services/session_service.dart';
import 'screens/welcome_screen.dart';
import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SessionService.instance.loadFromPrefs();
  await SelectedEnvironmentService.instance.ensureLoaded();
  runApp(const SynapseApp());
}

class SynapseApp extends StatelessWidget {
  const SynapseApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Synapse',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      initialRoute: '/welcome',
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
        '/dashboard': (_) => const DashboardPage(),
      },
    );
  }
}

