/// Environment summary (matches API `Environment`).
class EnvironmentSummary {
  const EnvironmentSummary({
    required this.id,
    required this.name,
    required this.location,
    this.iconKey,
    this.adminId,
  });

  final String id;
  final String name;
  final String location;
  final String? iconKey;
  final String? adminId;

  factory EnvironmentSummary.fromJson(Map<String, dynamic> json) {
    return EnvironmentSummary(
      id: json['id'] as String,
      name: (json['name'] as String?) ?? 'Environment',
      location: (json['location'] as String?) ?? '',
      iconKey: json['icon_key'] as String?,
      adminId: json['admin_id'] as String?,
    );
  }
}
