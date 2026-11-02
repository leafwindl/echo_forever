class PresenceThought {
  const PresenceThought({
    required this.thoughtId,
    required this.text,
    required this.salience,
    required this.shareable,
    required this.actionIntent,
    required this.createdAt,
  });

  factory PresenceThought.fromJson(Map<String, dynamic> json) {
    return PresenceThought(
      thoughtId: json['thought_id'] as String? ?? '',
      text: json['text'] as String? ?? '',
      salience: (json['salience'] as num?)?.toDouble() ?? 0,
      shareable: json['shareable'] as bool? ?? false,
      actionIntent: json['action_intent'] as String? ?? '',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
    );
  }

  final String thoughtId;
  final String text;
  final double salience;
  final bool shareable;
  final String actionIntent;
  final DateTime? createdAt;
}

class PresenceSnapshot {
  const PresenceSnapshot({
    required this.status,
    required this.enabled,
    required this.thoughtsUsed,
    required this.dailyThoughtBudget,
    this.lastUserMessageAt,
    this.lastTickAt,
    this.lastThoughtAt,
    this.lastDecision = '',
    this.lastDecisionReason = '',
    this.outreachSentCount = 0,
    this.outreachRepliedCount = 0,
    this.responseRate = 0,
    this.outreachDownshiftUntil,
    this.thoughts = const <PresenceThought>[],
  });

  factory PresenceSnapshot.fromJson(Map<String, dynamic> json) {
    return PresenceSnapshot(
      status: json['status'] as String? ?? 'idle',
      enabled: json['enabled'] as bool? ?? true,
      thoughtsUsed: json['thoughts_used'] as int? ?? 0,
      dailyThoughtBudget: json['daily_thought_budget'] as int? ?? 8,
      lastUserMessageAt: DateTime.tryParse(
        json['last_user_message_at'] as String? ?? '',
      ),
      lastTickAt: DateTime.tryParse(json['last_tick_at'] as String? ?? ''),
      lastThoughtAt: DateTime.tryParse(
        json['last_thought_at'] as String? ?? '',
      ),
      lastDecision: json['last_decision'] as String? ?? '',
      lastDecisionReason: json['last_decision_reason'] as String? ?? '',
      outreachSentCount: json['outreach_sent_count'] as int? ?? 0,
      outreachRepliedCount: json['outreach_replied_count'] as int? ?? 0,
      responseRate: (json['response_rate'] as num?)?.toDouble() ?? 0,
      outreachDownshiftUntil: DateTime.tryParse(
        json['outreach_downshift_until'] as String? ?? '',
      ),
      thoughts: (json['thoughts'] as List? ?? const <Object?>[])
          .whereType<Map<String, dynamic>>()
          .map(PresenceThought.fromJson)
          .toList(growable: false),
    );
  }

  final String status;
  final bool enabled;
  final int thoughtsUsed;
  final int dailyThoughtBudget;
  final DateTime? lastUserMessageAt;
  final DateTime? lastTickAt;
  final DateTime? lastThoughtAt;
  final String lastDecision;
  final String lastDecisionReason;
  final int outreachSentCount;
  final int outreachRepliedCount;
  final double responseRate;
  final DateTime? outreachDownshiftUntil;
  final List<PresenceThought> thoughts;

  String get statusLabel {
    switch (status) {
      case 'active':
        return '正在陪你';
      case 'sleeping':
        return '安静着';
      case 'focused':
        return '在专注';
      case 'resting':
        return '低功耗';
      default:
        return '闲着';
    }
  }

  bool get hasThoughts => thoughts.isNotEmpty;
}
