import 'package:echo_app/features/persona/domain/persona.dart';

class PersonaDraft {
  const PersonaDraft({
    required this.preferredName,
    required this.replyStyle,
    required this.replyLength,
    required this.supportMode,
    required this.proactivity,
    required this.avoidTopics,
    required this.aboutUser,
    required this.relationshipPace,
    required this.affectionStyle,
    required this.enabled,
  });

  factory PersonaDraft.defaults() {
    return const PersonaDraft(
      preferredName: '',
      replyStyle: PersonaReplyStyle.natural,
      replyLength: PersonaReplyLength.balanced,
      supportMode: PersonaSupportMode.balanced,
      proactivity: PersonaProactivity.balanced,
      avoidTopics: <String>[],
      aboutUser: '',
      relationshipPace: RelationshipPace.natural,
      affectionStyle: AffectionStyle.contextual,
      enabled: true,
    );
  }

  factory PersonaDraft.fromPersona(UserPersona persona) {
    return PersonaDraft(
      preferredName: persona.preferredName ?? '',
      replyStyle: persona.replyStyle,
      replyLength: persona.replyLength,
      supportMode: persona.supportMode,
      proactivity: persona.proactivity,
      avoidTopics: List<String>.of(persona.avoidTopics),
      aboutUser: persona.aboutUser ?? '',
      relationshipPace: persona.relationshipPace,
      affectionStyle: persona.affectionStyle,
      enabled: persona.enabled,
    );
  }

  final String preferredName;
  final PersonaReplyStyle replyStyle;
  final PersonaReplyLength replyLength;
  final PersonaSupportMode supportMode;
  final PersonaProactivity proactivity;
  final List<String> avoidTopics;
  final String aboutUser;
  final RelationshipPace relationshipPace;
  final AffectionStyle affectionStyle;
  final bool enabled;

  PersonaDraft copyWith({
    String? preferredName,
    PersonaReplyStyle? replyStyle,
    PersonaReplyLength? replyLength,
    PersonaSupportMode? supportMode,
    PersonaProactivity? proactivity,
    List<String>? avoidTopics,
    String? aboutUser,
    RelationshipPace? relationshipPace,
    AffectionStyle? affectionStyle,
    bool? enabled,
  }) {
    return PersonaDraft(
      preferredName: preferredName ?? this.preferredName,
      replyStyle: replyStyle ?? this.replyStyle,
      replyLength: replyLength ?? this.replyLength,
      supportMode: supportMode ?? this.supportMode,
      proactivity: proactivity ?? this.proactivity,
      avoidTopics: avoidTopics ?? this.avoidTopics,
      aboutUser: aboutUser ?? this.aboutUser,
      relationshipPace: relationshipPace ?? this.relationshipPace,
      affectionStyle: affectionStyle ?? this.affectionStyle,
      enabled: enabled ?? this.enabled,
    );
  }

  PersonaUpdate toUpdate() {
    return PersonaUpdate(
      preferredName: preferredName.trim(),
      replyStyle: replyStyle,
      replyLength: replyLength,
      supportMode: supportMode,
      proactivity: proactivity,
      avoidTopics: avoidTopics,
      aboutUser: aboutUser.trim(),
      relationshipPace: relationshipPace,
      affectionStyle: affectionStyle,
      enabled: enabled,
    );
  }
}
