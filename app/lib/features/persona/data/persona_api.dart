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
  static const companionshipResetPath = '/account/reset';

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

  Future<RelationshipStateDto> acceptRelationshipProposal(
    String proposalId,
  ) async {
    final response = await _client.post<Map<String, dynamic>>(
      '$relationshipPath/proposals/$proposalId/accept',
    );
    return RelationshipStateDto.fromJson(response.data!);
  }

  Future<void> deferRelationshipProposal(String proposalId) async {
    await _client.post<void>(
      '$relationshipPath/proposals/$proposalId/defer',
    );
  }

  Future<void> declineRelationshipProposal(String proposalId) async {
    await _client.post<void>(
      '$relationshipPath/proposals/$proposalId/decline',
    );
  }

  Future<void> resetCompanionship() async {
    await _client.post<void>(companionshipResetPath);
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

class RelationshipProposalDto {
  const RelationshipProposalDto({
    required this.proposalId,
    required this.direction,
    required this.directionLabel,
    required this.status,
    this.expiresAt,
  });

  factory RelationshipProposalDto.fromJson(Map<String, dynamic> json) {
    return RelationshipProposalDto(
      proposalId: json['proposal_id'] as String? ?? '',
      direction: json['direction'] as String? ?? '',
      directionLabel: json['direction_label'] as String? ?? '',
      status: json['status'] as String? ?? '',
      expiresAt: json['expires_at'] as String?,
    );
  }

  final String proposalId;
  final String direction;
  final String directionLabel;
  final String status;
  final String? expiresAt;
}

class RelationshipStateDto {
  const RelationshipStateDto({
    this.relationshipMode = RelationshipMode.friend,
    this.relationshipType = 'acquaintance',
    this.relationshipTypeLabel = '初识',
    required this.stage,
    required this.stageLabel,
    required this.interactionTurns,
    required this.activeDays,
    required this.affectionPermission,
    required this.schemaVersion,
    this.pendingProposal,
    this.createdAt,
    this.updatedAt,
  });

  const RelationshipStateDto.initial()
    : relationshipMode = RelationshipMode.friend,
      relationshipType = 'acquaintance',
      relationshipTypeLabel = '初识',
      stage = 'new',
      stageLabel = '初识',
      interactionTurns = 0,
      activeDays = 0,
      affectionPermission = 'unknown',
      schemaVersion = 2,
      pendingProposal = null,
      createdAt = null,
      updatedAt = null;

  factory RelationshipStateDto.fromJson(Map<String, dynamic> json) {
    final rawProposal = json['pending_proposal'];
    return RelationshipStateDto(
      relationshipMode: RelationshipMode.fromJson(json['relationship_mode']),
      relationshipType: json['relationship_type'] as String? ?? 'acquaintance',
      relationshipTypeLabel:
          json['relationship_type_label'] as String? ?? '初识',
      stage: json['stage'] as String? ?? 'new',
      stageLabel: json['stage_label'] as String? ?? '',
      interactionTurns: json['interaction_turns'] as int? ?? 0,
      activeDays: json['active_days'] as int? ?? 0,
      affectionPermission: json['affection_permission'] as String? ?? 'unknown',
      schemaVersion: json['schema_version'] as int? ?? 0,
      pendingProposal: rawProposal is Map<String, dynamic>
          ? RelationshipProposalDto.fromJson(rawProposal)
          : null,
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
    );
  }

  final RelationshipMode relationshipMode;
  final String relationshipType;
  final String relationshipTypeLabel;
  final String stage;
  final String stageLabel;
  final int interactionTurns;
  final int activeDays;
  final String affectionPermission;
  final int schemaVersion;
  final RelationshipProposalDto? pendingProposal;
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
