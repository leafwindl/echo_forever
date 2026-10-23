import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/persona/domain/persona.dart';

class PersonaApi {
  const PersonaApi(this._client);

  final DioClient _client;

  static const getPath = '/persona/me';
  static const updatePath = '/persona/me';
  static const resetPath = '/persona/me/reset';
  static const relationshipPath = '/relationship/me';
  static const relationshipResetPath = '/relationship/me/reset';

  Future<UserPersona> getPersona() async {
    final response = await _client.get<Map<String, dynamic>>(getPath);
    return UserPersonaJson.fromJson(response.data!);
  }

  Future<UserPersona> updatePersona(PersonaUpdate update) async {
    final response = await _client.put<Map<String, dynamic>>(
      updatePath,
      data: update.toJson(),
    );
    return UserPersonaJson.fromJson(response.data!);
  }

  Future<UserPersona> resetPersona() async {
    final response = await _client.post<Map<String, dynamic>>(resetPath);
    return UserPersonaJson.fromJson(response.data!);
  }

  Future<RelationshipStateDto> getRelationship() async {
    final response = await _client.get<Map<String, dynamic>>(relationshipPath);
    return RelationshipStateDto.fromJson(response.data!);
  }

  Future<RelationshipStateDto> resetRelationship() async {
    final response = await _client.post<Map<String, dynamic>>(
      relationshipResetPath,
    );
    return RelationshipStateDto.fromJson(response.data!);
  }

  Future<RelationshipStateDto> updateRelationshipMode(
    RelationshipMode mode,
  ) async {
    final response = await _client.put<Map<String, dynamic>>(
      relationshipPath,
      data: <String, dynamic>{'relationship_mode': mode.apiValue},
    );
    return RelationshipStateDto.fromJson(response.data!);
  }
}

class UserPersonaJson {
  const UserPersonaJson._();

  static UserPersona fromJson(Map<String, dynamic> json) {
    return UserPersona(
      preferredName: json['preferred_name'] as String?,
      replyStyle: PersonaReplyStyle.fromJson(json['reply_style']),
      replyLength: PersonaReplyLength.fromJson(json['reply_length']),
      supportMode: PersonaSupportMode.fromJson(json['support_mode']),
      proactivity: PersonaProactivity.fromJson(json['proactivity']),
      avoidTopics: (json['avoid_topics'] as List? ?? const <Object?>[])
          .whereType<String>()
          .toList(growable: false),
      aboutUser: json['about_user'] as String?,
      relationshipPace: RelationshipPace.fromJson(json['relationship_pace']),
      affectionStyle: AffectionStyle.fromJson(json['affection_style']),
      enabled: json['enabled'] as bool? ?? true,
      schemaVersion: json['schema_version'] as int? ?? 0,
      isCustomized: json['is_customized'] as bool? ?? false,
      onboardingCompleted: json['onboarding_completed'] as bool? ?? false,
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
    );
  }
}

class RelationshipStateDto {
  const RelationshipStateDto({
    this.relationshipMode = RelationshipMode.friend,
    required this.stage,
    required this.stageLabel,
    required this.interactionTurns,
    required this.activeDays,
    required this.affectionPermission,
    required this.schemaVersion,
    this.createdAt,
    this.updatedAt,
  });

  const RelationshipStateDto.initial()
    : relationshipMode = RelationshipMode.friend,
      stage = 'new',
      stageLabel = '初识',
      interactionTurns = 0,
      activeDays = 0,
      affectionPermission = 'unknown',
      schemaVersion = 2,
      createdAt = null,
      updatedAt = null;

  factory RelationshipStateDto.fromJson(Map<String, dynamic> json) {
    return RelationshipStateDto(
      relationshipMode: RelationshipMode.fromJson(json['relationship_mode']),
      stage: json['stage'] as String? ?? 'new',
      stageLabel: json['stage_label'] as String? ?? '',
      interactionTurns: json['interaction_turns'] as int? ?? 0,
      activeDays: json['active_days'] as int? ?? 0,
      affectionPermission: json['affection_permission'] as String? ?? 'unknown',
      schemaVersion: json['schema_version'] as int? ?? 0,
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
    );
  }

  final RelationshipMode relationshipMode;
  final String stage;
  final String stageLabel;
  final int interactionTurns;
  final int activeDays;
  final String affectionPermission;
  final int schemaVersion;
  final String? createdAt;
  final String? updatedAt;

  String get displayStageLabel => switch (stage) {
    'new' => '初识',
    'familiar' => '熟悉',
    'trusted' => '信赖',
    'close' => '亲近',
    _ => '正在了解',
  };
}
