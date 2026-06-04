import 'package:flutter/material.dart';

/// Matches your `devices` table: type, status (bool), current_value (numeric).
enum EnvironmentDeviceType {
  lamp,
  thermostat,
  plug,
  sensor,
  other,
}

/// Finer-grained control kind derived from `type` + `name`.
///
/// `devices.type` only has 5 buckets (Lamp/Thermostat/Plug/Sensor/Other), so
/// kitchen plugs like Fırın / Bulaşık / Çamaşır all collapse into "plug".
/// We sniff the user-facing name to surface the right control widgets:
///
///   - lamp        → on/off + brightness slider
///   - ac          → on/off + temperature slider (16–30 °C)
///   - thermostat  → on/off + temperature slider (16–30 °C)
///   - oven        → on/off + temperature (50–250 °C) + duration timer
///   - dishwasher  → on/off + program picker + remaining time
///   - washer      → on/off + program picker + remaining time
///   - plug        → on/off only
///   - sensor      → read-only value
///   - other       → on/off only
enum DeviceControlKind {
  lamp,
  ac,
  thermostat,
  oven,
  dishwasher,
  washer,
  plug,
  sensor,
  other,
}

extension EnvironmentDeviceTypeX on EnvironmentDeviceType {
  String get categoryTitle => switch (this) {
        EnvironmentDeviceType.lamp => 'Lamp',
        EnvironmentDeviceType.thermostat => 'Thermostat',
        EnvironmentDeviceType.plug => 'Plug',
        EnvironmentDeviceType.sensor => 'Sensor',
        EnvironmentDeviceType.other => 'Other',
      };

  /// Backend `device_type` enum value.
  String get apiValue => switch (this) {
        EnvironmentDeviceType.lamp => 'Lamp',
        EnvironmentDeviceType.thermostat => 'Thermostat',
        EnvironmentDeviceType.plug => 'Plug',
        EnvironmentDeviceType.sensor => 'Sensor',
        EnvironmentDeviceType.other => 'Other',
      };

  IconData get icon => switch (this) {
        EnvironmentDeviceType.lamp => Icons.lightbulb_rounded,
        EnvironmentDeviceType.thermostat => Icons.thermostat_rounded,
        EnvironmentDeviceType.plug => Icons.electrical_services_rounded,
        EnvironmentDeviceType.sensor => Icons.sensors_rounded,
        EnvironmentDeviceType.other => Icons.devices_other_rounded,
      };

  /// How to present [currentValue] on the card (until API defines units).
  String formatCurrentValue(double v) => switch (this) {
        EnvironmentDeviceType.lamp => 'Brightness ${v.round()}%',
        EnvironmentDeviceType.thermostat => '${v.toStringAsFixed(1)} °C',
        EnvironmentDeviceType.plug => '${v.toStringAsFixed(0)} W',
        EnvironmentDeviceType.sensor => 'Reading: ${v.toStringAsFixed(1)}',
        EnvironmentDeviceType.other => 'Value: ${v.toStringAsFixed(1)}',
      };
}

EnvironmentDeviceType environmentDeviceTypeFromApi(String raw) {
  switch (raw) {
    case 'Lamp':
      return EnvironmentDeviceType.lamp;
    case 'Thermostat':
      return EnvironmentDeviceType.thermostat;
    case 'Plug':
      return EnvironmentDeviceType.plug;
    case 'Sensor':
      return EnvironmentDeviceType.sensor;
    case 'Other':
    default:
      return EnvironmentDeviceType.other;
  }
}

class EnvironmentDevice {
  const EnvironmentDevice({
    required this.id,
    required this.name,
    required this.room,
    required this.type,
    required this.status,
    required this.currentValue,
  });

  final String id;
  final String name;
  final String room;
  final EnvironmentDeviceType type;
  final bool status;
  final double currentValue;

  EnvironmentDevice copyWith({
    String? id,
    String? name,
    String? room,
    EnvironmentDeviceType? type,
    bool? status,
    double? currentValue,
  }) {
    return EnvironmentDevice(
      id: id ?? this.id,
      name: name ?? this.name,
      room: room ?? this.room,
      type: type ?? this.type,
      status: status ?? this.status,
      currentValue: currentValue ?? this.currentValue,
    );
  }

  /// Sniff a finer control kind from `type` and the user-facing name.
  DeviceControlKind get controlKind {
    final lower = name.toLowerCase();
    bool has(Iterable<String> needles) =>
        needles.any((n) => lower.contains(n));

    if (has(const ['firin', 'fırın', 'oven'])) return DeviceControlKind.oven;
    if (has(const ['bulasik', 'bulaşık', 'dishwasher'])) {
      return DeviceControlKind.dishwasher;
    }
    if (has(const ['camasir', 'çamaşır', 'washing', 'washer'])) {
      return DeviceControlKind.washer;
    }
    if (has(const ['klima', ' ac', 'air condition', 'condition'])) {
      return DeviceControlKind.ac;
    }

    return switch (type) {
      EnvironmentDeviceType.lamp => DeviceControlKind.lamp,
      EnvironmentDeviceType.thermostat => DeviceControlKind.thermostat,
      EnvironmentDeviceType.plug => DeviceControlKind.plug,
      EnvironmentDeviceType.sensor => DeviceControlKind.sensor,
      EnvironmentDeviceType.other => DeviceControlKind.other,
    };
  }

  factory EnvironmentDevice.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    final idStr = rawId is int ? '$rawId' : rawId as String;
    final typeStr = json['type'] as String? ?? 'Other';
    final cv = json['current_value'];
    double current = 0;
    if (cv != null) {
      if (cv is num) {
        current = cv.toDouble();
      } else {
        current = double.tryParse(cv.toString()) ?? 0;
      }
    }
    final name = json['name'] as String? ?? 'Device';
    final room = json['room'] as String? ?? '';
    return EnvironmentDevice(
      id: idStr,
      name: name,
      room: room,
      type: environmentDeviceTypeFromApi(typeStr),
      status: json['status'] as bool? ?? false,
      currentValue: current,
    );
  }
}
