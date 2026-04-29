class EnvironmentMember {
  const EnvironmentMember({
    required this.userId,
    this.fullName,
    this.avatarKey,
  });

  final String userId;
  final String? fullName;
  final String? avatarKey;

  factory EnvironmentMember.fromJson(Map<String, dynamic> json) {
    return EnvironmentMember(
      userId: json['user_id'] as String,
      fullName: json['full_name'] as String?,
      avatarKey: json['avatar_key'] as String?,
    );
  }
}
