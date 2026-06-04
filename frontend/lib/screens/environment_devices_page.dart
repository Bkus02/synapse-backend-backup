import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

import '../models/environment_device.dart';
import '../models/environment_member.dart';
import '../models/environment_summary.dart';
import '../models/join_request.dart';
import '../services/device_api.dart';
import '../services/environment_api.dart';
import '../services/session_service.dart';
import '../services/tuya_lamp_api.dart';
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

  void _setDeviceLocal(EnvironmentDevice device, {bool? status, double? value}) {
    setState(() {
      final i = _devices.indexWhere((e) => e.id == device.id);
      if (i >= 0) {
        _devices[i] = _devices[i].copyWith(
          status: status,
          currentValue: value,
        );
      }
    });
  }

  void _showSnack(String message, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? Colors.redAccent : null,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Future<void> _patchDevice(
    EnvironmentDevice device, {
    bool? status,
    double? currentValue,
  }) async {
    final id = int.tryParse(device.id);
    if (id == null) return;
    try {
      await DeviceApi.patch(
        deviceId: id,
        status: status,
        currentValue: currentValue,
      );
    } on UserApiException catch (e) {
      _showSnack('Device update failed: ${e.message}', error: true);
    } catch (e) {
      _showSnack('Device update failed: $e', error: true);
    }
  }

  Future<void> _onDeviceToggle(EnvironmentDevice device, bool on) async {
    _setDeviceLocal(device, status: on);
    // Tuya lamp: forward command to the physical bulb if linked.
    if (device.type == EnvironmentDeviceType.lamp) {
      try {
        if (on) {
          await TuyaLampApi.turnOn();
        } else {
          await TuyaLampApi.turnOff();
        }
      } on UserApiException catch (e) {
        _setDeviceLocal(device, status: !on);
        _showSnack('Lamp command failed: ${e.message}', error: true);
        return;
      } catch (e) {
        _setDeviceLocal(device, status: !on);
        _showSnack('Lamp command failed: $e', error: true);
        return;
      }
    }
    // Persist on/off so other clients / dashboard reflect the change.
    await _patchDevice(device, status: on);
  }

  Future<void> _onLampBrightness(EnvironmentDevice device, double value) async {
    _setDeviceLocal(device, status: true, value: value);
    try {
      await TuyaLampApi.setBrightness(value.round());
    } on UserApiException catch (e) {
      _showSnack('Brightness failed: ${e.message}', error: true);
    } catch (e) {
      _showSnack('Brightness failed: $e', error: true);
    }
    await _patchDevice(device, currentValue: value);
  }

  Future<void> _onValueChange(EnvironmentDevice device, double value) async {
    _setDeviceLocal(device, value: value);
    await _patchDevice(device, currentValue: value);
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
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _AddDeviceSheet(
        accent: AppColors.accent,
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
              backgroundColor: AppColors.accent,
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
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: AppColors.accent.withValues(alpha: 0.14),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        environmentIconForKey(env.iconKey),
                        color: AppColors.accent,
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
                              color: AppColors.textSecondary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          SelectableText(
                            env.id,
                            style: theme.textTheme.titleMedium?.copyWith(
                              color: AppColors.accent,
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
                      color: AppColors.accent.withValues(alpha: 0.9),
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
                              color: AppColors.textSecondary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            env.location,
                            style: theme.textTheme.bodyLarge?.copyWith(
                              color: AppColors.textPrimary,
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
                color: AppColors.textPrimary,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            ..._joinRequests.map(
              (r) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Material(
                  color: AppColors.surface,
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
                                  color: AppColors.textPrimary,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text(
                                'ID: ${r.userId}',
                                style: TextStyle(
                                  color: AppColors.textPrimary.withValues(alpha: 0.45),
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
                            backgroundColor: AppColors.accent,
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
                  color: AppColors.textPrimary,
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
                      style: TextStyle(color: AppColors.textMuted),
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
                                color: AppColors.textSecondary,
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
                  color: AppColors.textPrimary,
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
                      color: AppColors.textSecondary,
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
              style: TextStyle(color: AppColors.textMuted, fontSize: 13),
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
                    color: AppColors.textPrimary.withValues(alpha: 0.85),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              ...list.map((device) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _DeviceCard(
                      device: device,
                      accent: AppColors.accent,
                      cardColor: AppColors.surface,
                      onRemove: () => _confirmRemoveDevice(device),
                      onStatusChanged: (on) => _onDeviceToggle(device, on),
                      onBrightnessChanged: device.type ==
                              EnvironmentDeviceType.lamp
                          ? (value) => _onLampBrightness(device, value)
                          : null,
                      onValueChanged: (value) =>
                          _onValueChange(device, value),
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

class _DeviceCard extends StatefulWidget {
  const _DeviceCard({
    required this.device,
    required this.accent,
    required this.cardColor,
    required this.onRemove,
    required this.onStatusChanged,
    required this.onValueChanged,
    this.onBrightnessChanged,
  });

  final EnvironmentDevice device;
  final Color accent;
  final Color cardColor;
  final VoidCallback onRemove;
  final ValueChanged<bool> onStatusChanged;
  final ValueChanged<double> onValueChanged;
  final ValueChanged<double>? onBrightnessChanged;

  @override
  State<_DeviceCard> createState() => _DeviceCardState();
}

class _DeviceCardState extends State<_DeviceCard> {
  /// Frontend-only timer (oven / dishwasher / washer countdown).
  /// Persisting durations would need a new column; for the demo we keep it
  /// in widget state and refresh it locally.
  Duration? _remaining;

  EnvironmentDevice get device => widget.device;

  /// Default per-kind current_value when the row is freshly inserted.
  double _defaultValue() => switch (device.controlKind) {
        DeviceControlKind.lamp => 50,
        DeviceControlKind.ac => 22,
        DeviceControlKind.thermostat => 22,
        DeviceControlKind.oven => 180,
        DeviceControlKind.dishwasher => 1,
        DeviceControlKind.washer => 1,
        _ => 0,
      };

  double get _effectiveValue =>
      device.currentValue == 0 ? _defaultValue() : device.currentValue;

  String _summaryLine() {
    final v = _effectiveValue;
    return switch (device.controlKind) {
      DeviceControlKind.lamp => 'Brightness ${v.round()}%',
      DeviceControlKind.ac => '${v.toStringAsFixed(1)} °C • AC',
      DeviceControlKind.thermostat => '${v.toStringAsFixed(1)} °C • Thermostat',
      DeviceControlKind.oven => '${v.round()} °C • Oven',
      DeviceControlKind.dishwasher =>
        'Program: ${_kProgramLabels[v.clamp(0, _kProgramLabels.length - 1).round()]}',
      DeviceControlKind.washer =>
        'Program: ${_kWasherLabels[v.clamp(0, _kWasherLabels.length - 1).round()]}',
      DeviceControlKind.plug => 'Smart plug',
      DeviceControlKind.sensor => 'Sensor: ${v.toStringAsFixed(1)}',
      DeviceControlKind.other => 'Device',
    };
  }

  IconData _kindIcon() => switch (device.controlKind) {
        DeviceControlKind.lamp => Icons.lightbulb_rounded,
        DeviceControlKind.ac => Icons.ac_unit_rounded,
        DeviceControlKind.thermostat => Icons.thermostat_rounded,
        DeviceControlKind.oven => Icons.local_fire_department_rounded,
        DeviceControlKind.dishwasher => Icons.dining_rounded,
        DeviceControlKind.washer => Icons.local_laundry_service_rounded,
        DeviceControlKind.plug => Icons.electrical_services_rounded,
        DeviceControlKind.sensor => Icons.sensors_rounded,
        DeviceControlKind.other => Icons.devices_other_rounded,
      };

  void _startCountdown(Duration duration) {
    if (!device.status) return;
    setState(() => _remaining = duration);
    _tick();
  }

  void _stopCountdown() {
    setState(() => _remaining = null);
  }

  Future<void> _tick() async {
    while (mounted && _remaining != null && _remaining!.inSeconds > 0) {
      await Future.delayed(const Duration(seconds: 1));
      if (!mounted || _remaining == null) return;
      setState(() {
        _remaining = _remaining! - const Duration(seconds: 1);
      });
    }
    if (mounted && _remaining != null && _remaining!.inSeconds == 0) {
      widget.onStatusChanged(false);
      setState(() => _remaining = null);
    }
  }

  String _fmtRemaining(Duration d) {
    final h = d.inHours.remainder(24).toString().padLeft(2, '0');
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return d.inHours > 0 ? '$h:$m:$s' : '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final kind = device.controlKind;

    return Material(
      color: widget.cardColor,
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
                    color: widget.accent.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(_kindIcon(), color: widget.accent, size: 26),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        device.name,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: AppColors.textPrimary,
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
                              ? AppColors.borderStrong
                              : AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: widget.onRemove,
                  icon: const Icon(Icons.delete_outline_rounded),
                  color: AppColors.textMuted,
                  tooltip: 'Remove device',
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _summaryLine(),
                      style: theme.textTheme.titleSmall?.copyWith(
                        color: widget.accent,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  if (_remaining != null) ...[
                    Icon(Icons.timer_rounded,
                        size: 16, color: AppColors.textSecondary),
                    const SizedBox(width: 4),
                    Text(
                      _fmtRemaining(_remaining!),
                      style: theme.textTheme.titleSmall?.copyWith(
                        color: AppColors.textPrimary,
                        fontWeight: FontWeight.w700,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Text(
                  'Off',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: device.status
                        ? AppColors.textMuted
                        : AppColors.textSecondary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Expanded(
                  child: Center(
                    child: Switch.adaptive(
                      value: device.status,
                      activeThumbColor: AppColors.textOnAccent,
                      activeTrackColor: widget.accent.withValues(alpha: 0.55),
                      inactiveThumbColor: AppColors.textSecondary,
                      inactiveTrackColor: AppColors.border,
                      onChanged: (on) {
                        widget.onStatusChanged(on);
                        if (!on) _stopCountdown();
                      },
                    ),
                  ),
                ),
                Text(
                  'On',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: device.status
                        ? AppColors.textSecondary
                        : AppColors.textMuted,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            // -------- Kind-specific controls --------
            if (kind == DeviceControlKind.lamp &&
                widget.onBrightnessChanged != null) ...[
              const SizedBox(height: 6),
              Row(
                children: [
                  Icon(Icons.brightness_low_rounded,
                      size: 18, color: AppColors.textSecondary),
                  Expanded(
                    child: Slider(
                      value: _effectiveValue.clamp(0, 100).toDouble(),
                      min: 0,
                      max: 100,
                      divisions: 20,
                      label: '${_effectiveValue.round()}%',
                      activeColor: widget.accent,
                      inactiveColor: AppColors.border,
                      onChanged: device.status
                          ? (v) => widget.onBrightnessChanged!(v)
                          : null,
                    ),
                  ),
                  Icon(Icons.brightness_high_rounded,
                      size: 18, color: AppColors.textSecondary),
                ],
              ),
            ],
            if (kind == DeviceControlKind.ac ||
                kind == DeviceControlKind.thermostat)
              _TempSliderRow(
                value: _effectiveValue.clamp(16, 30).toDouble(),
                min: 16,
                max: 30,
                unit: '°C',
                accent: widget.accent,
                enabled: device.status,
                onChanged: widget.onValueChanged,
              ),
            if (kind == DeviceControlKind.oven) ...[
              _TempSliderRow(
                value: _effectiveValue.clamp(50, 250).toDouble(),
                min: 50,
                max: 250,
                divisions: 20,
                unit: '°C',
                accent: widget.accent,
                enabled: device.status,
                onChanged: widget.onValueChanged,
              ),
              const SizedBox(height: 6),
              _TimerRow(
                accent: widget.accent,
                enabled: device.status,
                presets: const [15, 30, 45, 60, 90, 120],
                onStart: (mins) => _startCountdown(Duration(minutes: mins)),
                onStop: _stopCountdown,
                hasActiveTimer: _remaining != null,
              ),
            ],
            if (kind == DeviceControlKind.dishwasher)
              _ProgramPickerRow(
                labels: _kProgramLabels,
                durations: _kProgramDurations,
                value: _effectiveValue.clamp(0, _kProgramLabels.length - 1).round(),
                accent: widget.accent,
                enabled: device.status,
                onChanged: (idx) {
                  widget.onValueChanged(idx.toDouble());
                  _startCountdown(_kProgramDurations[idx]);
                },
              ),
            if (kind == DeviceControlKind.washer)
              _ProgramPickerRow(
                labels: _kWasherLabels,
                durations: _kWasherDurations,
                value: _effectiveValue.clamp(0, _kWasherLabels.length - 1).round(),
                accent: widget.accent,
                enabled: device.status,
                onChanged: (idx) {
                  widget.onValueChanged(idx.toDouble());
                  _startCountdown(_kWasherDurations[idx]);
                },
              ),
          ],
        ),
      ),
    );
  }
}

const List<String> _kProgramLabels = ['Eco', 'Normal', 'Intense', 'Quick'];
const List<Duration> _kProgramDurations = [
  Duration(hours: 2, minutes: 30),
  Duration(hours: 1, minutes: 30),
  Duration(hours: 2),
  Duration(minutes: 30),
];

const List<String> _kWasherLabels = ['Eco', 'Cotton', 'Delicate', 'Quick 30'];
const List<Duration> _kWasherDurations = [
  Duration(hours: 3),
  Duration(hours: 2),
  Duration(hours: 1, minutes: 10),
  Duration(minutes: 30),
];


class _TempSliderRow extends StatelessWidget {
  const _TempSliderRow({
    required this.value,
    required this.min,
    required this.max,
    required this.unit,
    required this.accent,
    required this.enabled,
    required this.onChanged,
    this.divisions,
  });

  final double value;
  final double min;
  final double max;
  final int? divisions;
  final String unit;
  final Color accent;
  final bool enabled;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        children: [
          Icon(Icons.thermostat_outlined,
              size: 18, color: AppColors.textSecondary),
          Expanded(
            child: Slider(
              value: value,
              min: min,
              max: max,
              divisions: divisions ?? (max - min).round(),
              label: '${value.toStringAsFixed(0)} $unit',
              activeColor: accent,
              inactiveColor: AppColors.border,
              onChanged: enabled ? onChanged : null,
            ),
          ),
          SizedBox(
            width: 56,
            child: Text(
              '${value.toStringAsFixed(0)} $unit',
              textAlign: TextAlign.right,
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}


class _TimerRow extends StatelessWidget {
  const _TimerRow({
    required this.accent,
    required this.enabled,
    required this.presets,
    required this.onStart,
    required this.onStop,
    required this.hasActiveTimer,
  });

  final Color accent;
  final bool enabled;
  final List<int> presets;
  final ValueChanged<int> onStart;
  final VoidCallback onStop;
  final bool hasActiveTimer;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Run duration',
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final m in presets)
                OutlinedButton(
                  onPressed: enabled ? () => onStart(m) : null,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: accent,
                    side: BorderSide(
                      color: enabled
                          ? accent.withValues(alpha: 0.5)
                          : AppColors.border,
                    ),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    minimumSize: const Size(0, 32),
                  ),
                  child: Text('$m min'),
                ),
              if (hasActiveTimer)
                TextButton.icon(
                  onPressed: onStop,
                  style: TextButton.styleFrom(
                    foregroundColor: Colors.redAccent,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    minimumSize: const Size(0, 32),
                  ),
                  icon: const Icon(Icons.stop_circle_outlined, size: 18),
                  label: const Text('Stop'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}


class _ProgramPickerRow extends StatelessWidget {
  const _ProgramPickerRow({
    required this.labels,
    required this.durations,
    required this.value,
    required this.accent,
    required this.enabled,
    required this.onChanged,
  });

  final List<String> labels;
  final List<Duration> durations;
  final int value;
  final Color accent;
  final bool enabled;
  final ValueChanged<int> onChanged;

  String _fmt(Duration d) {
    if (d.inHours == 0) return '${d.inMinutes} min';
    final mins = d.inMinutes.remainder(60);
    return mins == 0 ? '${d.inHours} h' : '${d.inHours} h $mins min';
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Program',
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (var i = 0; i < labels.length; i++)
                ChoiceChip(
                  selected: value == i,
                  selectedColor: accent.withValues(alpha: 0.25),
                  backgroundColor: AppColors.surfaceMuted,
                  side: BorderSide(
                    color: value == i ? accent : AppColors.border,
                  ),
                  label: Text(
                    '${labels[i]} • ${_fmt(durations[i])}',
                    style: TextStyle(
                      color: AppColors.textPrimary,
                      fontWeight: value == i ? FontWeight.w700 : FontWeight.w500,
                    ),
                  ),
                  onSelected: enabled ? (_) => onChanged(i) : null,
                ),
            ],
          ),
        ],
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

  bool _tuyaChecking = false;
  bool _tuyaConfigured = false;
  TuyaLampStatus? _tuyaStatus;
  String? _tuyaError;

  @override
  void initState() {
    super.initState();
    _maybeProbeTuya();
  }

  @override
  void dispose() {
    _name.dispose();
    _room.dispose();
    super.dispose();
  }

  Future<void> _maybeProbeTuya() async {
    if (_type != EnvironmentDeviceType.lamp) return;
    setState(() {
      _tuyaChecking = true;
      _tuyaError = null;
    });
    try {
      final configured = await TuyaLampApi.isConfigured();
      if (!mounted) return;
      if (!configured) {
        setState(() {
          _tuyaConfigured = false;
          _tuyaChecking = false;
        });
        return;
      }
      final status = await TuyaLampApi.status();
      if (!mounted) return;
      setState(() {
        _tuyaConfigured = true;
        _tuyaStatus = status;
        _tuyaChecking = false;
        if (_name.text.trim().isEmpty) {
          _name.text = status.name;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _tuyaConfigured = true; // configured but failed to read
        _tuyaError = e.toString();
        _tuyaChecking = false;
      });
    }
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
      final isLamp = _type == EnvironmentDeviceType.lamp;
      final useTuya = isLamp && _tuyaConfigured && _tuyaStatus != null;
      final initialBrightness = useTuya
          ? (_tuyaStatus!.brightnessPercent ?? 50).toDouble()
          : _defaultCurrentValue(_type);
      final initialOn = useTuya ? (_tuyaStatus!.isOn ?? false) : false;

      await DeviceApi.create(
        userId: widget.userId,
        environmentId: widget.environmentId,
        type: _type,
        name: _name.text,
        room: _room.text.trim().isEmpty ? null : _room.text,
        status: initialOn,
        currentValue: initialBrightness,
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
                  color: AppColors.textPrimary,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 6),
          Text(
            'Stored in your database. On/off and temperature sync can be added next.',
            style: TextStyle(
              color: AppColors.textPrimary.withValues(alpha: 0.45),
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _name,
            style: const TextStyle(color: AppColors.textPrimary),
            decoration: InputDecoration(
              labelText: 'Name',
              labelStyle: const TextStyle(color: AppColors.textSecondary),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppColors.border),
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
            style: const TextStyle(color: AppColors.textPrimary),
            decoration: InputDecoration(
              labelText: 'Room (optional)',
              labelStyle: const TextStyle(color: AppColors.textSecondary),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppColors.border),
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
              labelStyle: const TextStyle(color: AppColors.textSecondary),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppColors.border),
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
                dropdownColor: AppColors.surfaceMuted,
                style: const TextStyle(color: AppColors.textPrimary),
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
                          _maybeProbeTuya();
                        }
                      },
              ),
            ),
          ),
          if (_type == EnvironmentDeviceType.lamp) ...[
            const SizedBox(height: 12),
            _TuyaLampBanner(
              checking: _tuyaChecking,
              configured: _tuyaConfigured,
              status: _tuyaStatus,
              error: _tuyaError,
            ),
          ],
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
                      color: AppColors.textPrimary,
                    ),
                  )
                : Text(
                    _type == EnvironmentDeviceType.lamp &&
                            _tuyaConfigured &&
                            _tuyaStatus != null
                        ? 'Link & save'
                        : 'Save device',
                  ),
          ),
        ],
      ),
    );
  }
}

class _TuyaLampBanner extends StatelessWidget {
  const _TuyaLampBanner({
    required this.checking,
    required this.configured,
    required this.status,
    required this.error,
  });

  final bool checking;
  final bool configured;
  final TuyaLampStatus? status;
  final String? error;

  @override
  Widget build(BuildContext context) {
    if (checking) {
      return _wrap(
        bg: AppColors.surfaceMuted,
        border: AppColors.border,
        child: Row(
          children: const [
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            SizedBox(width: 12),
            Text(
              'Looking for Smart Life lamp…',
              style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
            ),
          ],
        ),
      );
    }
    if (!configured) {
      return _wrap(
        bg: AppColors.surfaceMuted,
        border: AppColors.border,
        child: const Text(
          'Tuya / Smart Life is not configured on the backend. '
          'Set TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, and TUYA_DEVICE_ID in .env to '
          'auto-link your lamp.',
          style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
        ),
      );
    }
    if (status == null) {
      return _wrap(
        bg: AppColors.surfaceMuted,
        border: Colors.redAccent.withValues(alpha: 0.4),
        child: Text(
          error ?? 'Could not reach the Smart Life lamp.',
          style: const TextStyle(color: Colors.redAccent, fontSize: 12),
        ),
      );
    }
    final s = status!;
    final brightness = s.brightnessPercent;
    return _wrap(
      bg: AppColors.accent.withValues(alpha: 0.08),
      border: AppColors.accent.withValues(alpha: 0.45),
      child: Row(
        children: [
          Icon(Icons.lightbulb_rounded, color: AppColors.accent, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Smart Life lamp will be linked',
                  style: TextStyle(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${s.name} • ${s.online ? "online" : "offline"}'
                  '${brightness != null ? " • $brightness%" : ""}',
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _wrap({
    required Color bg,
    required Color border,
    required Widget child,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: border),
      ),
      child: child,
    );
  }
}
