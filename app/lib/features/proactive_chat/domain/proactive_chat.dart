class ProactiveChatPreferences {
  const ProactiveChatPreferences({
    required this.enabled,
    required this.allowEchoScheduling,
    required this.allowSpontaneousChat,
    required this.timezone,
    required this.quietStart,
    required this.quietEnd,
    required this.explicitReminderQuietPolicy,
    required this.notificationPreview,
    this.pausedUntil,
    this.pauseIndefinite = false,
  });

  const ProactiveChatPreferences.defaults()
    : enabled = false,
      allowEchoScheduling = true,
      allowSpontaneousChat = false,
      timezone = 'Asia/Shanghai',
      quietStart = '22:30',
      quietEnd = '08:00',
      explicitReminderQuietPolicy = 'defer',
      notificationPreview = false,
      pausedUntil = null,
      pauseIndefinite = false;

  factory ProactiveChatPreferences.fromJson(Map<String, dynamic> json) {
    return ProactiveChatPreferences(
      enabled: json['enabled'] as bool? ?? false,
      allowEchoScheduling: json['allow_echo_scheduling'] as bool? ?? true,
      allowSpontaneousChat: json['allow_spontaneous_chat'] as bool? ?? false,
      timezone: json['timezone'] as String? ?? 'Asia/Shanghai',
      quietStart: _shortTime(json['quiet_start']),
      quietEnd: _shortTime(json['quiet_end']),
      explicitReminderQuietPolicy:
          json['explicit_reminder_quiet_policy'] as String? ?? 'defer',
      notificationPreview: json['notification_preview'] as bool? ?? false,
      pausedUntil: json['paused_until'] as String?,
      pauseIndefinite: json['pause_indefinite'] as bool? ?? false,
    );
  }

  final bool enabled;
  final bool allowEchoScheduling;
  final bool allowSpontaneousChat;
  final String timezone;
  final String quietStart;
  final String quietEnd;
  final String explicitReminderQuietPolicy;
  final bool notificationPreview;
  final String? pausedUntil;
  final bool pauseIndefinite;

  bool get paused => pauseIndefinite || pausedUntil != null;

  ProactiveChatPreferences copyWith({
    bool? enabled,
    bool? allowEchoScheduling,
    bool? allowSpontaneousChat,
    String? timezone,
    String? quietStart,
    String? quietEnd,
    String? explicitReminderQuietPolicy,
    bool? notificationPreview,
  }) => ProactiveChatPreferences(
    enabled: enabled ?? this.enabled,
    allowEchoScheduling: allowEchoScheduling ?? this.allowEchoScheduling,
    allowSpontaneousChat: allowSpontaneousChat ?? this.allowSpontaneousChat,
    timezone: timezone ?? this.timezone,
    quietStart: quietStart ?? this.quietStart,
    quietEnd: quietEnd ?? this.quietEnd,
    explicitReminderQuietPolicy:
        explicitReminderQuietPolicy ?? this.explicitReminderQuietPolicy,
    notificationPreview: notificationPreview ?? this.notificationPreview,
    pausedUntil: pausedUntil,
    pauseIndefinite: pauseIndefinite,
  );

  Map<String, dynamic> toJson() => <String, dynamic>{
    'enabled': enabled,
    'allow_echo_scheduling': allowEchoScheduling,
    'allow_spontaneous_chat': allowSpontaneousChat,
    'timezone': timezone,
    'quiet_start': quietStart,
    'quiet_end': quietEnd,
    'explicit_reminder_quiet_policy': explicitReminderQuietPolicy,
    'notification_preview': notificationPreview,
  };
}

class ChatSchedule {
  const ChatSchedule({
    required this.scheduleId,
    required this.createdBy,
    required this.scheduleType,
    required this.intent,
    required this.label,
    required this.timezone,
    required this.nextRunAt,
    required this.status,
  });

  factory ChatSchedule.fromJson(Map<String, dynamic> json) => ChatSchedule(
    scheduleId: json['schedule_id'] as String? ?? '',
    createdBy: json['created_by'] as String? ?? '',
    scheduleType: json['schedule_type'] as String? ?? 'once',
    intent: json['intent'] as String? ?? '',
    label: json['user_visible_label'] as String? ?? '',
    timezone: json['timezone'] as String? ?? 'Asia/Shanghai',
    nextRunAt: DateTime.tryParse(
      json['next_run_at'] as String? ?? '',
    )?.toLocal(),
    status: json['status'] as String? ?? 'active',
  );

  final String scheduleId;
  final String createdBy;
  final String scheduleType;
  final String intent;
  final String label;
  final String timezone;
  final DateTime? nextRunAt;
  final String status;

  bool get isActive => status == 'active';
  bool get isPaused => status == 'paused';
  String get displayLabel => label.trim().isEmpty ? intent : label;
}

String _shortTime(Object? value) {
  final raw = value?.toString() ?? '';
  return raw.length >= 5 ? raw.substring(0, 5) : '00:00';
}
