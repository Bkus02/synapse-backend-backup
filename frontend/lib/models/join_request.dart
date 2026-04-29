class JoinRequest {
  const JoinRequest({
    required this.id,
    required this.environmentId,
    required this.userId,
    this.requesterName,
    this.requesterAvatarKey,
    this.createdAt,
  });

  final int id;
  final String environmentId;
  final String userId;
  final String? requesterName;
  final String? requesterAvatarKey;
  final String? createdAt;

  factory JoinRequest.fromJson(Map<String, dynamic> json) {
    return JoinRequest(
      id: json['id'] as int,
      environmentId: json['environment_id'] as String,
      userId: json['user_id'] as String,
      requesterName: json['requester_name'] as String?,
      requesterAvatarKey: json['requester_avatar_key'] as String?,
      createdAt: json['created_at'] as String?,
    );
  }
}
