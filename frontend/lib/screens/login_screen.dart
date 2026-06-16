import 'package:flutter/material.dart';

import '../services/auth_api.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';
import '../theme/app_colors.dart';
import 'register_screen.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({
    super.key,
    this.prefillEmail,
    this.initialSnack,
  });

  final String? prefillEmail;
  final String? initialSnack;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _emailCtrl;
  late final TextEditingController _passwordCtrl;

  bool _showCredentials = false;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    final pre = widget.prefillEmail?.trim();
    _showCredentials = pre != null && pre.isNotEmpty;
    _emailCtrl = TextEditingController(text: pre ?? '');
    _passwordCtrl = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _maybeResumeSession();
    });
  }

  Future<void> _maybeResumeSession() async {
    if (!mounted) return;
    final msg = widget.initialSnack;
    if (msg != null && msg.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(msg),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
    if (!SessionService.instance.hasToken) return;
    try {
      final me = await AuthApi.fetchMe();
      await SessionService.instance.setUser(me);
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed('/dashboard');
    } on UserApiException {
      await SessionService.instance.clear();
    } catch (_) {
      // Backend kapalıysa login ekranında kal.
    }
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  InputDecoration _decoration(String label) {
    return InputDecoration(labelText: label);
  }

  Future<void> _onSignIn() async {
    if (!_formKey.currentState!.validate()) return;
    if (_submitting) return;

    setState(() => _submitting = true);
    FocusScope.of(context).unfocus();

    try {
      final result = await UserApi.login(
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
      );
      await SessionService.instance.setSession(
        user: result.user,
        accessToken: result.accessToken,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed('/dashboard');
    } on UserApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.message),
          backgroundColor: AppColors.error,
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Connection error. Is the backend running?'),
          backgroundColor: AppColors.error,
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _openCredentials() {
    setState(() => _showCredentials = true);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              Expanded(
                child: Center(
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.psychology,
                          size: 72,
                          color: AppColors.accent,
                        ),
                        const SizedBox(height: 20),
                        Text(
                          'SYNAPSE',
                          textAlign: TextAlign.center,
                          style: theme.textTheme.displaySmall?.copyWith(
                            color: AppColors.textPrimary,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 6,
                            fontSize: 36,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          _showCredentials
                              ? 'Sign in with email and password'
                              : 'How would you like to continue?',
                          textAlign: TextAlign.center,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: AppColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 32),
                        if (!_showCredentials) ...[
                          SizedBox(
                            height: 52,
                            width: double.infinity,
                            child: OutlinedButton(
                              style: OutlinedButton.styleFrom(
                                foregroundColor: AppColors.textPrimary,
                                side: const BorderSide(color: AppColors.border),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                backgroundColor: AppColors.surface,
                              ),
                              onPressed: _openCredentials,
                              child: const Text(
                                'Continue with Email',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 16),
                          SizedBox(
                            height: 52,
                            width: double.infinity,
                            child: ElevatedButton(
                              style: ElevatedButton.styleFrom(
                                backgroundColor: AppColors.accent,
                                foregroundColor: AppColors.textOnAccent,
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16),
                                ),
                              ),
                              onPressed: _openCredentials,
                              child: const Text(
                                'Continue with Synapse',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                        ] else ...[
                          Form(
                            key: _formKey,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                TextFormField(
                                  controller: _emailCtrl,
                                  keyboardType: TextInputType.emailAddress,
                                  autofillHints: const [AutofillHints.email],
                                  style: const TextStyle(color: AppColors.textPrimary),
                                  decoration: _decoration('Email'),
                                  validator: (v) {
                                    if (v == null || v.trim().isEmpty) {
                                      return 'Required';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 16),
                                TextFormField(
                                  controller: _passwordCtrl,
                                  obscureText: true,
                                  autofillHints: const [AutofillHints.password],
                                  style: const TextStyle(color: AppColors.textPrimary),
                                  decoration: _decoration('Password'),
                                  onFieldSubmitted: (_) => _onSignIn(),
                                  validator: (v) {
                                    if (v == null || v.isEmpty) {
                                      return 'Required';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 8),
                                Align(
                                  alignment: Alignment.centerLeft,
                                  child: TextButton(
                                    onPressed: () {
                                      setState(() {
                                        _showCredentials = false;
                                      });
                                    },
                                    child: const Text('Back'),
                                  ),
                                ),
                                const SizedBox(height: 16),
                                SizedBox(
                                  height: 52,
                                  child: ElevatedButton(
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: AppColors.accent,
                                      foregroundColor: AppColors.textOnAccent,
                                      elevation: 0,
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(16),
                                      ),
                                    ),
                                    onPressed: _submitting ? null : _onSignIn,
                                    child: _submitting
                                        ? const SizedBox(
                                            width: 24,
                                            height: 24,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              color: AppColors.textPrimary,
                                            ),
                                          )
                                        : const Text(
                                            'Sign in',
                                            style: TextStyle(
                                              fontSize: 16,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Wrap(
                  alignment: WrapAlignment.center,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      "Don't have an account? ",
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                    GestureDetector(
                      onTap: () {
                        Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => const RegisterScreen(),
                          ),
                        );
                      },
                      child: Text(
                        'Sign up',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: AppColors.accent,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
