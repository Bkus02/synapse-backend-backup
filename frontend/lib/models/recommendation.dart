class Recommendation {
  const Recommendation({
    required this.id,
    required this.userId,
    required this.type,
    required this.trigger,
    required this.target,
    required this.context,
    required this.finalConfidence,
    required this.status,
    this.createdAt,
  });

  final String id;
  final String userId;
  final String type;
  final String trigger;
  final String target;
  final String context;
  final double finalConfidence;
  final String status;
  final String? createdAt;

  String get headline => '$trigger → $target';

  String get body {
    if (context.trim().isNotEmpty) return context.trim();
    return 'Synapse detected a habit pattern (${(finalConfidence * 100).round()}% confidence).';
  }

  factory Recommendation.fromJson(Map<String, dynamic> json) {
    return Recommendation(
      id: json['id'] as String,
      userId: json['user_id'] as String,
      type: json['type'] as String? ?? 'habit',
      trigger: json['trigger'] as String? ?? '',
      target: json['target'] as String? ?? '',
      context: json['context'] as String? ?? '',
      finalConfidence: (json['final_confidence'] as num?)?.toDouble() ?? 0,
      status: json['status'] as String? ?? 'Pending',
      createdAt: json['created_at'] as String?,
    );
  }
}
