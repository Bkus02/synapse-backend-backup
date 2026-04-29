import 'package:flutter/material.dart';

import '../models/environment_device.dart';
import '../models/environment_member.dart';
import '../models/environment_summary.dart';
import '../models/join_request.dart';
import '../services/device_api.dart';
import '../services/environment_api.dart';
import '../services/session_service.dart';
import '../services/user_api.dart';
import '../utils/environment_visuals.dart';

/// Devices for one environment, grouped by `type` (Lamp, Thermostat, Plug, Sensor).
class EnvironmentDevicesPage extends StatefulWidget {
  const EnvironmentDevicesPage({
    super.key,
    required this.environment,
  });

  final EnvironmentSummary environment;

  @override
  State<EnvironmentDevicesPage> createState() => _EnvironmentDevicesPageState();
}

class _EnvironmentDevicesPageState extends State<EnvironmentDevicesPage> {
  static const _card = Color(0xFF0C1021);
  static const _accent = Color(0xFF4C6FFF);

  List<EnvironmentDevice> _devices = [];
  bool _loadingDevices = true;
  String? _devicesError;

  List<EnvironmentMember> _members = [];
  List<JoinRequest> _joinRequests = [];
  bool _loadingPeople = true;
  String? _peopleError;

  static const _typeOrder = [
    EnvironmentDeviceType.lamp,
    EnvironmentDeviceType.thermostat,
    EnvironmentDeviceType.plug,
    EnvironmentDeviceType.sensor,
    EnvironmentDeviceType.other,
  ];

  @override
  void initState() {
    super.initState();
    _loadDevices();
    _loadPeople();
  }

  Future<void> _loadDevices() async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) {
      if (mounted) {
        setState(() {
          _devices = [];
          _loadingDevices = false;
          _devicesError = 'Sign in to load devices.';
        });
      }
      return;
    }
    setState(() {
      _loadingDevices = true;
      _devicesError = null;
    });
    try {
      final list = await DeviceApi.listForEnvironment(
        environmentId: widget.environment.id,
        userId: uid,
      );
      if (mounted) {
        setState(() {
          _devices = list;
          _loadingDevices = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _devicesError = e.toString();
          _loadingDevices = false;
        });
      }
    }
  }

  Future<void> _confirmRemoveDevice(EnvironmentDevice device) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    final id = int.tryParse(device.id);
    if (id == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove device'),
        content: Text(
          'Remove "${device.name}" from this environment? This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: Colors.redAccent),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await DeviceApi.delete(deviceId: id, userId: uid);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Device removed'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        _loadDevices();
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
    }
  }

  void _openAddDeviceSheet() {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Sign in to add devices.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF15192E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _AddDeviceSheet(
        accent: _accent,
        environmentId: widget.environment.id,
        userId: uid,
        onAdded: () {
          Navigator.pop(ctx);
          _loadDevices();
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Device added'),
              behavior: SnackBarBehavior.floating,
            ),
          );
        },
      ),
    );
  }

  bool get _isAdmin {
    final uid = SessionService.instance.user?['id'] as String?;
    final aid = widget.environment.adminId;
    return uid != null && aid != null && uid == aid;
  }

  Future<void> _loadPeople() async {
    setState(() {
      _loadingPeople = true;
      _peopleError = null;
    });
    try {
      final members =
          await EnvironmentApi.listMembers(widget.environment.id);
      List<JoinRequest> pending = [];
      if (_isAdmin) {
        final uid = SessionService.instance.user?['id'] as String?;
        if (uid != null) {
          pending = await EnvironmentApi.listJoinRequests(
            environmentId: widget.environment.id,
            adminUserId: uid,
          );
        }
      }
      if (mounted) {
        setState(() {
          _members = members;
          _joinRequests = pending;
          _loadingPeople = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _peopleError = e.toString();
          _loadingPeople = false;
        });
      }
    }
  }

  Future<void> _approve(JoinRequest r) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    try {
      await EnvironmentApi.approveJoinRequest(
        environmentId: widget.environment.id,
        requestId: r.id,
        adminUserId: uid,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Membership approved'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        _loadPeople();
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
    }
  }

  Future<void> _reject(JoinRequest r) async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return;
    try {
      await EnvironmentApi.rejectJoinRequest(
        environmentId: widget.environment.id,
        requestId: r.id,
        adminUserId: uid,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Request rejected'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        _loadPeople();
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
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final env = widget.environment;

    final grouped = <EnvironmentDeviceType, List<EnvironmentDevice>>{};
    for (final d in _devices) {
      grouped.putIfAbsent(d.type, () => []).add(d);
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(env.name),
      ),
      floatingActionButton: SessionService.instance.user?['id'] != null
          ? FloatingActionButton.extended(
              onPressed: _loadingDevices ? null : _openAddDeviceSheet,
              backgroundColor: _accent,
              icon: const Icon(Icons.add_rounded),
              label: const Text('Add device'),
            )
          : null,
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: _card,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.white10),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: _accent.withValues(alpha: 0.14),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        environmentIconForKey(env.iconKey),
                        color: _accent,
                        size: 24,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'environment_id',
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: Colors.white54,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          SelectableText(
                            env.id,
                            style: theme.textTheme.titleMedium?.copyWith(
                              color: _accent,
                              fontWeight: FontWeight.w700,
                              fontFamily: 'monospace',
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.location_on_outlined,
                      color: _accent.withValues(alpha: 0.9),
                      size: 20,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Location',
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: Colors.white54,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            env.location,
                            style: theme.textTheme.bodyLarge?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w600,
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
          if (_isAdmin && _joinRequests.isNotEmpty) ...[
            const SizedBox(height: 20),
            Text(
              'Join requests',
              style: theme.textTheme.titleSmall?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            ..._joinRequests.map(
              (r) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Material(
                  color: _card,
                  borderRadius: BorderRadius.circular(14),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        memberAvatar(
                          avatarKey: r.requesterAvatarKey,
                          fullName: r.requesterName ?? r.userId,
                          radius: 22,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                r.requesterName ?? r.userId,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text(
                                'ID: ${r.userId}',
                                style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.45),
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ),
                        TextButton(
                          onPressed: () => _reject(r),
                          child: const Text('Reject'),
                        ),
                        const SizedBox(width: 4),
                        FilledButton(
                          onPressed: () => _approve(r),
                          style: FilledButton.styleFrom(
                            backgroundColor: _accent,
                          ),
                          child: const Text('Approve'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Members',
                style: theme.textTheme.titleSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (_loadingPeople)
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
            ],
          ),
          if (_peopleError != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _peopleError!,
                style: const TextStyle(color: Colors.redAccent, fontSize: 12),
              ),
            ),
          const SizedBox(height: 10),
          SizedBox(
            height: 88,
            child: _members.isEmpty && !_loadingPeople
                ? const Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'No members yet.',
                      style: TextStyle(color: Colors.white38),
                    ),
                  )
                : ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: _members.length,
                    separatorBuilder: (context, index) =>
                        const SizedBox(width: 12),
                    itemBuilder: (context, i) {
                      final m = _members[i];
                      return SizedBox(
                        width: 72,
                        child: Column(
                          children: [
                            memberAvatar(
                              avatarKey: m.avatarKey,
                              fullName: m.fullName,
                              radius: 26,
                            ),
                            const SizedBox(height: 6),
                            Text(
                              m.fullName?.trim().isNotEmpty == true
                                  ? m.fullName!.trim()
                                  : m.userId,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
          const SizedBox(height: 22),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Devices',
                style: theme.textTheme.titleSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Row(
                children: [
                  if (_loadingDevices)
                    const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  else
                    IconButton(
                      onPressed: _loadDevices,
                      icon: const Icon(Icons.refresh_rounded),
                      color: Colors.white54,
                      tooltip: 'Refresh devices',
                    ),
                ],
              ),
            ],
          ),
          if (_devicesError != null)
            Padding(
              padding: const EdgeInsets.only(top: 8, bottom: 8),
              child: Text(
                _devicesError!,
                style: const TextStyle(color: Colors.redAccent, fontSize: 12),
              ),
            ),
          if (!_loadingDevices &&
              _devices.isEmpty &&
              _devicesError == null) ...[
            const SizedBox(height: 8),
            const Text(
              'No devices yet. Tap Add device to register one (controls sync later).',
              style: TextStyle(color: Colors.white38, fontSize: 13),
            ),
            const SizedBox(height: 12),
          ],
          ..._typeOrder.expand((type) {
            final list = grouped[type];
            if (list == null || list.isEmpty) {
              return <Widget>[];
            }
            return [
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  type.categoryTitle,
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: Colors.white.withValues(alpha: 0.85),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              ...list.map((device) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _DeviceCard(
                      device: device,
                      accent: _accent,
                      cardColor: _card,
                      onRemove: () => _confirmRemoveDevice(device),
                      onStatusChanged: (on) {
                        setState(() {
                          final i = _devices.indexWhere((e) => e.id == device.id);
                          if (i >= 0) {
                            _devices[i] = _devices[i].copyWith(status: on);
                          }
                        });
                      },
                    ),
                  )),
              const SizedBox(height: 8),
            ];
          }),
        ],
      ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  const _DeviceCard({
    required this.device,
    required this.accent,
    required this.cardColor,
    required this.onRemove,
    required this.onStatusChanged,
  });

  final EnvironmentDevice device;
  final Color accent;
  final Color cardColor;
  final VoidCallback onRemove;
  final ValueChanged<bool> onStatusChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final t = device.type;

    return Material(
      color: cardColor,
      borderRadius: BorderRadius.circular(16),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(
                    t.icon,
                    color: accent,
                    size: 26,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        device.name,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        device.room.trim().isEmpty
                            ? 'No room set'
                            : device.room,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: device.room.trim().isEmpty
                              ? Colors.white30
                              : Colors.white54,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: onRemove,
                  icon: const Icon(Icons.delete_outline_rounded),
                  color: Colors.white38,
                  tooltip: 'Remove device',
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white10),
              ),
              child: Text(
                t.formatCurrentValue(device.currentValue),
                style: theme.textTheme.titleSmall?.copyWith(
                  color: accent,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Text(
                  'Off',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: device.status ? Colors.white38 : Colors.white70,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Expanded(
                  child: Center(
                    child: Switch.adaptive(
                      value: device.status,
                      activeThumbColor: Colors.white,
                      activeTrackColor: accent.withValues(alpha: 0.55),
                      inactiveThumbColor: Colors.white54,
                      inactiveTrackColor: Colors.white24,
                      onChanged: onStatusChanged,
                    ),
                  ),
                ),
                Text(
                  'On',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: device.status ? Colors.white70 : Colors.white38,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

double _defaultCurrentValue(EnvironmentDeviceType type) {
  return switch (type) {
    EnvironmentDeviceType.lamp => 50,
    EnvironmentDeviceType.thermostat => 21,
    EnvironmentDeviceType.plug => 0,
    EnvironmentDeviceType.sensor => 0,
    EnvironmentDeviceType.other => 0,
  };
}

class _AddDeviceSheet extends StatefulWidget {
  const _AddDeviceSheet({
    required this.accent,
    required this.environmentId,
    required this.userId,
    required this.onAdded,
  });

  final Color accent;
  final String environmentId;
  final String userId;
  final VoidCallback onAdded;

  @override
  State<_AddDeviceSheet> createState() => _AddDeviceSheetState();
}

class _AddDeviceSheetState extends State<_AddDeviceSheet> {
  final _name = TextEditingController();
  final _room = TextEditingController();
  EnvironmentDeviceType _type = EnvironmentDeviceType.lamp;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _room.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Enter a device name'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      await DeviceApi.create(
        userId: widget.userId,
        environmentId: widget.environmentId,
        type: _type,
        name: _name.text,
        room: _room.text.trim().isEmpty ? null : _room.text,
        currentValue: _defaultCurrentValue(_type),
      );
      if (mounted) {
        widget.onAdded();
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
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    const types = [
      EnvironmentDeviceType.lamp,
      EnvironmentDeviceType.thermostat,
      EnvironmentDeviceType.plug,
      EnvironmentDeviceType.sensor,
    ];
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Add device',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 6),
          Text(
            'Stored in your database. On/off and temperature sync can be added next.',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.45),
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _name,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              labelText: 'Name',
              labelStyle: const TextStyle(color: Colors.white54),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Colors.white24),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: widget.accent),
              ),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _room,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              labelText: 'Room (optional)',
              labelStyle: const TextStyle(color: Colors.white54),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Colors.white24),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: widget.accent),
              ),
            ),
          ),
          const SizedBox(height: 16),
          InputDecorator(
            decoration: InputDecoration(
              labelText: 'Type',
              labelStyle: const TextStyle(color: Colors.white54),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Colors.white24),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: widget.accent),
              ),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<EnvironmentDeviceType>(
                value: _type,
                isExpanded: true,
                dropdownColor: const Color(0xFF1E2440),
                style: const TextStyle(color: Colors.white),
                items: types
                    .map(
                      (t) => DropdownMenuItem(
                        value: t,
                        child: Text(t.categoryTitle),
                      ),
                    )
                    .toList(),
                onChanged: _saving
                    ? null
                    : (v) {
                        if (v != null) {
                          setState(() => _type = v);
                        }
                      },
              ),
            ),
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _saving ? null : _submit,
            style: FilledButton.styleFrom(
              backgroundColor: widget.accent,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: _saving
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Text('Save device'),
          ),
        ],
      ),
    );
  }
}
