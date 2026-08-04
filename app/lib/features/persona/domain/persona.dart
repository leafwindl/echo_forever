const maxPreferredNameLength = 40;
const maxAboutUserLength = 300;
const maxAvoidTopics = 5;
const maxAvoidTopicLength = 40;

enum PersonaReplyStyle {
  natural('natural'),
  concise('concise'),
  lively('lively');

  const PersonaReplyStyle(this.apiValue);

  final String apiValue;

  static PersonaReplyStyle fromJson(Object? value) {
    return PersonaReplyStyle.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => PersonaReplyStyle.natural,
    );
  }
}

enum PersonaReplyLength {
  short('short'),
  balanced('balanced'),
  detailed('detailed');

  const PersonaReplyLength(this.apiValue);

  final String apiValue;

  static PersonaReplyLength fromJson(Object? value) {
    return PersonaReplyLength.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => PersonaReplyLength.balanced,
    );
  }
}

enum PersonaSupportMode {
  comfort('comfort'),
  advice('advice'),
  balanced('balanced');

  const PersonaSupportMode(this.apiValue);

  final String apiValue;

  static PersonaSupportMode fromJson(Object? value) {
    return PersonaSupportMode.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => PersonaSupportMode.balanced,
    );
  }
}

enum PersonaProactivity {
  quiet('quiet'),
  balanced('balanced'),
  active('active');

  const PersonaProactivity(this.apiValue);

  final String apiValue;

  static PersonaProactivity fromJson(Object? value) {
    return PersonaProactivity.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => PersonaProactivity.balanced,
    );
  }
}

enum RelationshipPace {
  slow('slow'),
  natural('natural'),
  open('open');

  const RelationshipPace(this.apiValue);

  final String apiValue;

  static RelationshipPace fromJson(Object? value) {
    return RelationshipPace.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => RelationshipPace.natural,
    );
  }
}

enum AffectionStyle {
  restrained('restrained'),
  contextual('contextual'),
  expressive('expressive');

  const AffectionStyle(this.apiValue);

  final String apiValue;

  static AffectionStyle fromJson(Object? value) {
    return AffectionStyle.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => AffectionStyle.contextual,
    );
  }
}

extension PersonaReplyStyleLabel on PersonaReplyStyle {
  String get label => switch (this) {
    PersonaReplyStyle.natural => '自然',
    PersonaReplyStyle.concise => '简洁',
    PersonaReplyStyle.lively => '活泼',
  };
}

extension PersonaReplyLengthLabel on PersonaReplyLength {
  String get label => switch (this) {
    PersonaReplyLength.short => '短一些',
    PersonaReplyLength.balanced => '适中',
    PersonaReplyLength.detailed => '详细',
  };
}

extension PersonaSupportModeLabel on PersonaSupportMode {
  String get label => switch (this) {
    PersonaSupportMode.comfort => '先陪伴',
    PersonaSupportMode.advice => '给建议',
    PersonaSupportMode.balanced => '平衡',
  };
}

extension PersonaProactivityLabel on PersonaProactivity {
  String get label => switch (this) {
    PersonaProactivity.quiet => '安静',
    PersonaProactivity.balanced => '适中',
    PersonaProactivity.active => '主动',
  };
}

extension RelationshipPaceLabel on RelationshipPace {
  String get label => switch (this) {
    RelationshipPace.slow => '慢慢来',
    RelationshipPace.natural => '自然',
    RelationshipPace.open => '开放',
  };
}

extension AffectionStyleLabel on AffectionStyle {
  String get label => switch (this) {
    AffectionStyle.restrained => '克制',
    AffectionStyle.contextual => '看语境',
    AffectionStyle.expressive => '更有温度',
  };
}

class PersonaUpdate {
  const PersonaUpdate({
    this.preferredName,
    this.replyStyle = PersonaReplyStyle.natural,
    this.replyLength = PersonaReplyLength.balanced,
    this.supportMode = PersonaSupportMode.balanced,
    this.proactivity = PersonaProactivity.balanced,
    this.avoidTopics = const <String>[],
    this.aboutUser,
    this.relationshipPace = RelationshipPace.natural,
    this.affectionStyle = AffectionStyle.contextual,
    this.enabled = true,
  });

  final String? preferredName;
  final PersonaReplyStyle replyStyle;
  final PersonaReplyLength replyLength;
  final PersonaSupportMode supportMode;
  final PersonaProactivity proactivity;
  final List<String> avoidTopics;
  final String? aboutUser;
  final RelationshipPace relationshipPace;
  final AffectionStyle affectionStyle;
  final bool enabled;

  Map<String, Object?> toJson() => <String, Object?>{
    'preferred_name': preferredName,
    'reply_style': replyStyle.apiValue,
    'reply_length': replyLength.apiValue,
    'support_mode': supportMode.apiValue,
    'proactivity': proactivity.apiValue,
    'avoid_topics': avoidTopics,
    'about_user': aboutUser,
    'relationship_pace': relationshipPace.apiValue,
    'affection_style': affectionStyle.apiValue,
    'enabled': enabled,
  };
}

PersonaUpdate normalizePersonaUpdate(
  PersonaUpdate update, {
  bool requirePreferredName = false,
}) {
  final preferredName = _normalizeOptionalText(
    update.preferredName,
    maxPreferredNameLength,
    '称呼最多 $maxPreferredNameLength 个字',
  );
  if (requirePreferredName && preferredName == null) {
    throw const FormatException('先告诉 Echo 怎么称呼你');
  }
  final aboutUser = _normalizeOptionalText(
    update.aboutUser,
    maxAboutUserLength,
    '关于你最多 $maxAboutUserLength 个字',
  );
  final avoidTopics = _normalizeAvoidTopics(update.avoidTopics);
  return PersonaUpdate(
    preferredName: preferredName,
    replyStyle: update.replyStyle,
    replyLength: update.replyLength,
    supportMode: update.supportMode,
    proactivity: update.proactivity,
    avoidTopics: avoidTopics,
    aboutUser: aboutUser,
    relationshipPace: update.relationshipPace,
    affectionStyle: update.affectionStyle,
    enabled: update.enabled,
  );
}

String? _normalizeOptionalText(
  String? value,
  int maximumLength,
  String errorMessage,
) {
  final cleanValue = value?.trim();
  if (cleanValue == null || cleanValue.isEmpty) {
    return null;
  }
  if (cleanValue.length > maximumLength) {
    throw FormatException(errorMessage);
  }
  return cleanValue;
}

List<String> _normalizeAvoidTopics(List<String> values) {
  if (values.length > maxAvoidTopics) {
    throw const FormatException('最多添加 5 个话题');
  }
  final normalized = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final cleanValue = value.trim();
    if (cleanValue.isEmpty) {
      continue;
    }
    if (cleanValue.length > maxAvoidTopicLength) {
      throw const FormatException('单个话题最多 40 个字');
    }
    final key = cleanValue.toLowerCase();
    if (seen.add(key)) {
      normalized.add(cleanValue);
    }
  }
  if (normalized.length > maxAvoidTopics) {
    throw const FormatException('最多添加 5 个话题');
  }
  return normalized;
}

class UserPersona {
  const UserPersona({
    required this.replyStyle,
    required this.replyLength,
    required this.supportMode,
    required this.proactivity,
    required this.avoidTopics,
    required this.relationshipPace,
    required this.affectionStyle,
    required this.enabled,
    required this.schemaVersion,
    required this.isCustomized,
    required this.onboardingCompleted,
    this.preferredName,
    this.aboutUser,
    this.createdAt,
    this.updatedAt,
  });

  const UserPersona.defaults()
    : preferredName = null,
      replyStyle = PersonaReplyStyle.natural,
      replyLength = PersonaReplyLength.balanced,
      supportMode = PersonaSupportMode.balanced,
      proactivity = PersonaProactivity.balanced,
      avoidTopics = const <String>[],
      aboutUser = null,
      relationshipPace = RelationshipPace.natural,
      affectionStyle = AffectionStyle.contextual,
      enabled = true,
      schemaVersion = 3,
      isCustomized = false,
      onboardingCompleted = false,
      createdAt = null,
      updatedAt = null;

  final String? preferredName;
  final PersonaReplyStyle replyStyle;
  final PersonaReplyLength replyLength;
  final PersonaSupportMode supportMode;
  final PersonaProactivity proactivity;
  final List<String> avoidTopics;
  final String? aboutUser;
  final RelationshipPace relationshipPace;
  final AffectionStyle affectionStyle;
  final bool enabled;
  final int schemaVersion;
  final bool isCustomized;
  final bool onboardingCompleted;
  final String? createdAt;
  final String? updatedAt;

  UserPersona copyWith({
    String? preferredName,
    bool clearPreferredName = false,
    PersonaReplyStyle? replyStyle,
    PersonaReplyLength? replyLength,
    PersonaSupportMode? supportMode,
    PersonaProactivity? proactivity,
    List<String>? avoidTopics,
    bool clearAvoidTopics = false,
    String? aboutUser,
    bool clearAboutUser = false,
    RelationshipPace? relationshipPace,
    AffectionStyle? affectionStyle,
    bool? enabled,
    int? schemaVersion,
    bool? isCustomized,
    bool? onboardingCompleted,
    String? createdAt,
    bool clearCreatedAt = false,
    String? updatedAt,
    bool clearUpdatedAt = false,
  }) {
    return UserPersona(
      preferredName: clearPreferredName
          ? null
          : preferredName ?? this.preferredName,
      replyStyle: replyStyle ?? this.replyStyle,
      replyLength: replyLength ?? this.replyLength,
      supportMode: supportMode ?? this.supportMode,
      proactivity: proactivity ?? this.proactivity,
      avoidTopics: clearAvoidTopics
          ? <String>[]
          : avoidTopics ?? this.avoidTopics,
      aboutUser: clearAboutUser ? null : aboutUser ?? this.aboutUser,
      relationshipPace: relationshipPace ?? this.relationshipPace,
      affectionStyle: affectionStyle ?? this.affectionStyle,
      enabled: enabled ?? this.enabled,
      schemaVersion: schemaVersion ?? this.schemaVersion,
      isCustomized: isCustomized ?? this.isCustomized,
      onboardingCompleted: onboardingCompleted ?? this.onboardingCompleted,
      createdAt: clearCreatedAt ? null : createdAt ?? this.createdAt,
      updatedAt: clearUpdatedAt ? null : updatedAt ?? this.updatedAt,
    );
  }

  PersonaUpdate toUpdate() {
    return PersonaUpdate(
      preferredName: preferredName,
      replyStyle: replyStyle,
      replyLength: replyLength,
      supportMode: supportMode,
      proactivity: proactivity,
      avoidTopics: List<String>.of(avoidTopics),
      aboutUser: aboutUser,
      relationshipPace: relationshipPace,
      affectionStyle: affectionStyle,
      enabled: enabled,
    );
  }
}
