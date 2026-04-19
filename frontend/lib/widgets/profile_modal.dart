import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/session_service.dart';
import '../services/user_api.dart';
import '../utils/environment_visuals.dart';

/// Bottom sheet profile panel. Call: `ProfileModal.show(context);`
class ProfileModal {
  ProfileModal._();

  static const _sheetColor = Color(0xFF0C1021);

  static void show(BuildContext context) {
    final heightFraction = 0.9;
    final topRadius = 25.0;

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black54,
      builder: (sheetContext) {
        final media = MediaQuery.of(sheetContext);
        final sheetHeight = media.size.height * heightFraction;

        return Padding(
          padding: EdgeInsets.only(bottom: media.viewInsets.bottom),
          child: Align(
            alignment: Alignment.bottomCenter,
            child: ClipRRect(
              borderRadius:
                  BorderRadius.vertical(top: Radius.circular(topRadius)),
              child: Material(
                color: _sheetColor,
                child: SizedBox(
                  height: sheetHeight,
                  width: double.infinity,
                  child: _ProfileSheet(rootContext: context),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _ProfileSheet extends StatefulWidget {
  const _ProfileSheet({required this.rootContext});

  final BuildContext rootContext;

  @override
  State<_ProfileSheet> createState() => _ProfileSheetState();
}

class _ProfileSheetState extends State<_ProfileSheet> {
  final _formKey = GlobalKey<FormState>();

  late final TextEditingController _nameCtrl;
  late final TextEditingController _emailCtrl;
  late final TextEditingController _passwordCtrl;
  late final TextEditingController _heightCtrl;
  late final TextEditingController _weightCtrl;
  late final TextEditingController _ageCtrl;
  late final TextEditingController _locationCtrl;

  late String _avatarKey;

  bool _saving = false;

  Map<String, dynamic>? get _user => SessionService.instance.user;

  @override
  void initState() {
    super.initState();
    final u = _user;
    _nameCtrl = TextEditingController(text: u?['full_name']?.toString() ?? '');
    _emailCtrl = TextEditingController(text: u?['email']?.toString() ?? '');
    _passwordCtrl = TextEditingController();
    _heightCtrl = TextEditingController(
      text: u?['height'] != null ? '${u!['height']}' : '',
    );
    _weightCtrl = TextEditingController(
      text: u?['weight'] != null ? '${u!['weight']}' : '',
    );
    _ageCtrl = TextEditingController(
      text: u?['age'] != null ? '${u!['age']}' : '',
    );
    _locationCtrl =
        TextEditingController(text: u?['location']?.toString() ?? '');
    final rawAvatar = u?['avatar_key']?.toString().trim();
    _avatarKey =
        (rawAvatar != null && rawAvatar.isNotEmpty) ? rawAvatar : 'person';
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _heightCtrl.dispose();
    _weightCtrl.dispose();
    _ageCtrl.dispose();
    _locationCtrl.dispose();
    super.dispose();
  }

  InputDecoration _decoration(String label) {
    return InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: Colors.white54),
      filled: true,
      fillColor: const Color(0xFF151A2E),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Colors.white24),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Color(0xFF4C6FFF)),
      ),
    );
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final id = _user?['id']?.toString();
    if (id == null || id.isEmpty) return;

    final height = int.tryParse(_heightCtrl.text.trim());
    final weight = int.tryParse(_weightCtrl.text.trim());
    final age = int.tryParse(_ageCtrl.text.trim());
    if (height == null || weight == null || age == null) return;

    setState(() => _saving = true);
    FocusScope.of(context).unfocus();

    try {
      final updated = await UserApi.updateUser(
        userId: id,
        fullName: _nameCtrl.text.trim(),
        email: _emailCtrl.text.trim(),
        height: height,
        weight: weight,
        age: age,
        location: _locationCtrl.text.trim(),
        newPassword: _passwordCtrl.text.isEmpty ? null : _passwordCtrl.text,
        avatarKey: _avatarKey,
      );
      await SessionService.instance.setUser(updated);
      _passwordCtrl.clear();
      if (!mounted) return;
      if (widget.rootContext.mounted) {
        ScaffoldMessenger.of(widget.rootContext).showSnackBar(
          const SnackBar(
            content: Text('Profile updated'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
      if (mounted) {
        Navigator.of(context).pop();
      }
    } on UserApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.message),
          backgroundColor: Colors.redAccent,
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Connection error'),
          backgroundColor: Colors.redAccent,
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _signOut() async {
    await SessionService.instance.clear();
    if (!mounted) return;
    Navigator.of(context).pop();
    if (!widget.rootContext.mounted) return;
    Navigator.of(widget.rootContext).pushNamedAndRemoveUntil(
      '/login',
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_user == null) {
      return Column(
        children: [
          const SizedBox(height: 12),
          _handleBar(),
          const Expanded(
            child: Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'Sign up first to set up your profile.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white70, fontSize: 16),
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(20),
            child: TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
          ),
        ],
      );
    }

    return Column(
      children: [
        const SizedBox(height: 12),
        _handleBar(),
        const SizedBox(height: 16),
        Text(
          'Profile',
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: Form(
            key: _formKey,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              children: [
                Text(
                  'Profile picture',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.55),
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: kUserAvatarChoices.map((e) {
                    final sel = _avatarKey == e.key;
                    return InkWell(
                      onTap: () => setState(() => _avatarKey = e.key),
                      borderRadius: BorderRadius.circular(12),
                      child: Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: sel
                              ? const Color(0xFF4C6FFF).withValues(alpha: 0.25)
                              : const Color(0xFF151A2E),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: sel
                                ? const Color(0xFF4C6FFF)
                                : Colors.white12,
                          ),
                        ),
                        child: Icon(
                          userAvatarIconForKey(e.key) ?? Icons.person,
                          color: Colors.white70,
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _nameCtrl,
                  style: const TextStyle(color: Colors.white),
                  decoration: _decoration('Full name'),
                  validator: (v) =>
                      v == null || v.trim().isEmpty ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _emailCtrl,
                  style: const TextStyle(color: Colors.white),
                  keyboardType: TextInputType.emailAddress,
                  decoration: _decoration('Email'),
                  validator: (v) =>
                      v == null || v.trim().isEmpty ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _passwordCtrl,
                  style: const TextStyle(color: Colors.white),
                  obscureText: true,
                  decoration: _decoration('New password (optional)'),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _heightCtrl,
                        style: const TextStyle(color: Colors.white),
                        keyboardType: TextInputType.number,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                        ],
                        decoration: _decoration('Height (cm)'),
                        validator: (v) =>
                            int.tryParse(v?.trim() ?? '') == null
                                ? 'Number'
                                : null,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextFormField(
                        controller: _weightCtrl,
                        style: const TextStyle(color: Colors.white),
                        keyboardType: TextInputType.number,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                        ],
                        decoration: _decoration('Weight (kg)'),
                        validator: (v) =>
                            int.tryParse(v?.trim() ?? '') == null
                                ? 'Number'
                                : null,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _ageCtrl,
                  style: const TextStyle(color: Colors.white),
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: _decoration('Age'),
                  validator: (v) =>
                      int.tryParse(v?.trim() ?? '') == null ? 'Number' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _locationCtrl,
                  style: const TextStyle(color: Colors.white),
                  decoration: _decoration('Location'),
                  validator: (v) =>
                      v == null || v.trim().isEmpty ? 'Required' : null,
                ),
                const SizedBox(height: 24),
                SizedBox(
                  height: 48,
                  width: double.infinity,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF4C6FFF),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    onPressed: _saving ? null : _save,
                    child: _saving
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text(
                            'Save',
                            style: TextStyle(fontWeight: FontWeight.w700),
                          ),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  height: 48,
                  width: double.infinity,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFD32F2F),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    onPressed: _saving ? null : _signOut,
                    child: const Text(
                      'Sign out',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _handleBar() {
    return Center(
      child: Container(
        width: 40,
        height: 4,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.28),
          borderRadius: BorderRadius.circular(999),
        ),
      ),
    );
  }
}
