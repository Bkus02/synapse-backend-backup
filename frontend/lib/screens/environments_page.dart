import 'package:flutter/material.dart';

import '../models/environment_summary.dart';
import '../services/environment_api.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';
import '../utils/environment_visuals.dart';
import 'environment_devices_page.dart';

class EnvironmentsPage extends StatefulWidget {
  const EnvironmentsPage({
    super.key,
    this.pendingOpenEnvironmentId,
    this.onPendingOpenConsumed,
  });

  /// When set (e.g. from notification → Environments tab), opens this environment’s detail.
  final String? pendingOpenEnvironmentId;
  final VoidCallback? onPendingOpenConsumed;

  @override
  State<EnvironmentsPage> createState() => _EnvironmentsPageState();
}

class _EnvironmentsPageState extends State<EnvironmentsPage> {
  static const _accent = Color(0xFF4C6FFF);
  static const _card = Color(0xFF0C1021);

  List<EnvironmentSummary> _envs = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    SessionService.instance.addListener(_onSession);
    _reload();
  }

  @override
  void dispose() {
    SessionService.instance.removeListener(_onSession);
    super.dispose();
  }

  void _onSession() {
    if (mounted) {
      _reload();
    }
  }

  Future<void> _reload() async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) {
      setState(() {
        _envs = [];
        _loading = false;
        _error = null;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await EnvironmentApi.listForUser(uid);
      if (mounted) {
        setState(() {
          _envs = list;
          _loading = false;
        });
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _tryConsumePendingOpen();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = e.toString();
        });
      }
    }
  }

  @override
  void didUpdateWidget(covariant EnvironmentsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.pendingOpenEnvironmentId !=
        oldWidget.pendingOpenEnvironmentId) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _tryConsumePendingOpen();
      });
    }
  }

  void _tryConsumePendingOpen() {
    final id = widget.pendingOpenEnvironmentId;
    if (id == null || _loading || !mounted) return;
    EnvironmentSummary? match;
    for (final e in _envs) {
      if (e.id == id) {
        match = e;
        break;
      }
    }
    if (match == null) return;
    widget.onPendingOpenConsumed?.call();
    if (!mounted) return;
    Navigator.of(context)
        .push<void>(
      MaterialPageRoute<void>(
        builder: (_) => EnvironmentDevicesPage(environment: match!),
      ),
    )
        .then((_) {
      if (mounted) {
        _reload();
      }
    });
  }

  String? get _userId => SessionService.instance.user?['id'] as String?;

  void _requireUser(VoidCallback onOk) {
    if (_userId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please sign in first.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    onOk();
  }

  Future<void> _openAddEnvironment() async {
    _requireUser(() async {
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (ctx) => _AddEnvironmentSheet(
          adminId: _userId!,
          onCreated: (_) {
            Navigator.pop(ctx);
            _reload();
          },
        ),
      );
    });
  }

  Future<void> _openJoinEnvironment() async {
    _requireUser(() async {
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (ctx) => _JoinEnvironmentSheet(
          userId: _userId!,
          onDone: () {
            Navigator.pop(ctx);
            _reload();
          },
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: RefreshIndicator(
        color: _accent,
        onRefresh: _reload,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              sliver: SliverToBoxAdapter(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _ActionPill(
                        icon: Icons.add_home_outlined,
                        title: 'Add Environment',
                        subtitle: 'Create a new space',
                        accent: _accent,
                        card: _card,
                        onTap: _openAddEnvironment,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _ActionPill(
                        icon: Icons.link_rounded,
                        title: 'Join Environment',
                        subtitle: 'Join with an environment ID',
                        accent: _accent,
                        card: _card,
                        onTap: _openJoinEnvironment,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              sliver: SliverToBoxAdapter(
                child: Text(
                  'My Environments',
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
            if (_loading)
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: Center(child: CircularProgressIndicator()),
                ),
              )
            else if (_error != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _error!,
                    style: const TextStyle(color: Colors.redAccent),
                  ),
                ),
              )
            else if (_envs.isEmpty)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _userId == null
                        ? 'Sign in to see your environments.'
                        : 'No environments yet. Add one or join above.',
                    style: const TextStyle(color: Colors.white54),
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverList.separated(
                  itemCount: _envs.length,
                  separatorBuilder: (context, index) =>
                      const SizedBox(height: 10),
                  itemBuilder: (context, index) {
                    final env = _envs[index];
                    return _EnvironmentCard(
                      environment: env,
                      accent: _accent,
                      card: _card,
                      onTap: () {
                        Navigator.of(context).push<void>(
                          MaterialPageRoute<void>(
                            builder: (_) => EnvironmentDevicesPage(
                              environment: env,
                            ),
                          ),
                        ).then((_) => _reload());
                      },
                    );
                  },
                ),
              ),
            const SliverToBoxAdapter(child: SizedBox(height: 24)),
          ],
        ),
      ),
    );
  }
}

class _ActionPill extends StatelessWidget {
  const _ActionPill({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    required this.accent,
    required this.card,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color accent;
  final Color card;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: card,
      borderRadius: BorderRadius.circular(18),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 18, 14, 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: accent, size: 28),
              const SizedBox(height: 12),
              Text(
                title,
                style: theme.textTheme.titleSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                subtitle,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: Colors.white54,
                  height: 1.35,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EnvironmentCard extends StatelessWidget {
  const _EnvironmentCard({
    required this.environment,
    required this.onTap,
    required this.accent,
    required this.card,
  });

  final EnvironmentSummary environment;
  final VoidCallback onTap;
  final Color accent;
  final Color card;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final icon = environmentIconForKey(environment.iconKey);

    return Material(
      color: card,
      borderRadius: BorderRadius.circular(16),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: accent.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(icon, color: accent, size: 22),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      environment.name,
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  Icon(
                    Icons.chevron_right_rounded,
                    color: Colors.white.withValues(alpha: 0.35),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.location_on_outlined,
                    size: 18,
                    color: accent.withValues(alpha: 0.85),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Location',
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: Colors.white.withValues(alpha: 0.45),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          environment.location,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: Colors.white.withValues(alpha: 0.88),
                            height: 1.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AddEnvironmentSheet extends StatefulWidget {
  const _AddEnvironmentSheet({
    required this.adminId,
    required this.onCreated,
  });

  final String adminId;
  final void Function(EnvironmentSummary env) onCreated;

  @override
  State<_AddEnvironmentSheet> createState() => _AddEnvironmentSheetState();
}

class _AddEnvironmentSheetState extends State<_AddEnvironmentSheet> {
  final _nameCtrl = TextEditingController();
  final _locCtrl = TextEditingController();
  String? _suggestedId;
  String _iconKey = kEnvironmentIconChoices.first.key;
  bool _loadingId = true;
  bool _submitting = false;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _fetchId();
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _locCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetchId() async {
    try {
      final id = await EnvironmentApi.suggestEnvironmentId();
      if (mounted) {
        setState(() {
          _suggestedId = id;
          _loadingId = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loadError = e.toString();
          _loadingId = false;
        });
      }
    }
  }

  Future<void> _submit() async {
    if (_suggestedId == null || _nameCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Name and ID are required')),
      );
      return;
    }
    if (_locCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Location is required')),
      );
      return;
    }
    setState(() => _submitting = true);
    try {
      final env = await EnvironmentApi.create(
        id: _suggestedId!,
        name: _nameCtrl.text.trim(),
        location: _locCtrl.text.trim(),
        adminId: widget.adminId,
        iconKey: _iconKey,
      );
      if (mounted) {
        widget.onCreated(env);
      }
    } on UserApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message), backgroundColor: Colors.redAccent),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Connection error'),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;

    return Padding(
      padding: EdgeInsets.only(bottom: bottom),
      child: Container(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.92,
        ),
        decoration: const BoxDecoration(
          color: Color(0xFF0C1021),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(999),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'New environment',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Environment ID',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 12),
              ),
              const SizedBox(height: 6),
              if (_loadingId)
                const LinearProgressIndicator()
              else if (_loadError != null)
                Text(_loadError!, style: const TextStyle(color: Colors.redAccent))
              else
                SelectableText(
                  _suggestedId ?? '—',
                  style: const TextStyle(
                    color: Color(0xFF4C6FFF),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    fontFamily: 'monospace',
                  ),
                ),
              const SizedBox(height: 16),
              TextField(
                controller: _nameCtrl,
                style: const TextStyle(color: Colors.white),
                decoration: _fieldDeco('Environment name (e.g. Home)'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _locCtrl,
                style: const TextStyle(color: Colors.white),
                decoration: _fieldDeco('Location'),
              ),
              const SizedBox(height: 16),
              Text(
                'Appearance',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 12),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: kEnvironmentIconChoices.map((e) {
                  final selected = _iconKey == e.key;
                  return InkWell(
                    onTap: () => setState(() => _iconKey = e.key),
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: selected
                            ? const Color(0xFF4C6FFF).withValues(alpha: 0.25)
                            : const Color(0xFF151A2E),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: selected
                              ? const Color(0xFF4C6FFF)
                              : Colors.white12,
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            environmentIconForKey(e.key),
                            color: Colors.white70,
                            size: 20,
                          ),
                          const SizedBox(width: 6),
                          Text(
                            e.value,
                            style: const TextStyle(color: Colors.white, fontSize: 13),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 24),
              SizedBox(
                height: 48,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF4C6FFF),
                    foregroundColor: Colors.white,
                  ),
                  onPressed: _submitting || _loadingId ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text('Create'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  InputDecoration _fieldDeco(String label) {
    return InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: Colors.white54),
      filled: true,
      fillColor: const Color(0xFF151A2E),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
    );
  }
}

class _JoinEnvironmentSheet extends StatefulWidget {
  const _JoinEnvironmentSheet({
    required this.userId,
    required this.onDone,
  });

  final String userId;
  final VoidCallback onDone;

  @override
  State<_JoinEnvironmentSheet> createState() => _JoinEnvironmentSheetState();
}

class _JoinEnvironmentSheetState extends State<_JoinEnvironmentSheet> {
  final _idCtrl = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _idCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final raw = _idCtrl.text.trim().toUpperCase();
    if (raw.isEmpty) return;
    setState(() => _submitting = true);
    try {
      await EnvironmentApi.requestJoin(
        environmentId: raw,
        userId: widget.userId,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Request sent. You will be added when an admin approves.',
            ),
            behavior: SnackBarBehavior.floating,
          ),
        );
        widget.onDone();
      }
    } on UserApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e.message),
            backgroundColor: Colors.redAccent,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Connection error'),
            backgroundColor: Colors.redAccent,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottom),
      child: Container(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        decoration: const BoxDecoration(
          color: Color(0xFF0C1021),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Join environment',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Enter the ID from your environment admin (e.g. H0000001).',
              style: TextStyle(color: Colors.white54, fontSize: 13),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _idCtrl,
              style: const TextStyle(
                color: Colors.white,
                fontFamily: 'monospace',
                letterSpacing: 0.5,
              ),
              textCapitalization: TextCapitalization.characters,
              decoration: InputDecoration(
                hintText: 'H0000001',
                hintStyle: TextStyle(color: Colors.white.withValues(alpha: 0.3)),
                filled: true,
                fillColor: const Color(0xFF151A2E),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 20),
            SizedBox(
              height: 48,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF4C6FFF),
                  foregroundColor: Colors.white,
                ),
                onPressed: _submitting ? null : _submit,
                child: _submitting
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('Send join request'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
