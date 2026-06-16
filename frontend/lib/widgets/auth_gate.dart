import 'package:flutter/material.dart';

import '../services/auth_api.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';

/// Redirects unauthenticated users away from protected routes.
class AuthGate extends StatefulWidget {
  const AuthGate({
    super.key,
    required this.child,
  });

  final Widget child;

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool _checking = true;
  bool _allowed = false;

  @override
  void initState() {
    super.initState();
    _verify();
  }

  Future<void> _verify() async {
    if (!SessionService.instance.hasToken) {
      if (mounted) {
        setState(() {
          _checking = false;
          _allowed = false;
        });
        _goLogin();
      }
      return;
    }
    try {
      final me = await AuthApi.fetchMe();
      await SessionService.instance.setUser(me);
      if (mounted) {
        setState(() {
          _checking = false;
          _allowed = true;
        });
      }
    } on UserApiException {
      await SessionService.instance.clear();
      if (mounted) {
        setState(() {
          _checking = false;
          _allowed = false;
        });
        _goLogin(snack: 'Session expired. Please sign in again.');
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _checking = false;
          _allowed = false;
        });
        _goLogin(snack: 'Could not verify session. Check the backend.');
      }
    }
  }

  void _goLogin({String? snack}) {
    if (!mounted) return;
    Navigator.of(context).pushNamedAndRemoveUntil(
      '/login',
      (route) => false,
      arguments: snack == null
          ? null
          : <String, String>{'snack': snack},
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_checking) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }
    if (!_allowed) {
      return const Scaffold(
        body: SizedBox.shrink(),
      );
    }
    return widget.child;
  }
}
