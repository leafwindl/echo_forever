import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/data/persona_repository.dart';
import 'package:echo_app/features/persona/domain/persona.dart';

import '../../support/fake_preferences_store.dart';

class FakePersonaRepository implements PersonaRepository {
  FakePersonaRepository({
    UserPersona? persona,
    RelationshipStateDto? relationship,
  }) : persona = persona ?? personaFixture(),
       relationship = relationship ?? const RelationshipStateDto.initial();

  UserPersona persona;
  RelationshipStateDto relationship;
  UserPersona? nextUpdatedPersona;
  UserPersona? nextResetPersona;
  RelationshipStateDto? nextResetRelationship;
  Object? getPersonaError;
  Object? updatePersonaError;
  Object? resetPersonaError;
  Object? getRelationshipError;
  Object? resetRelationshipError;
  int getPersonaCalls = 0;
  int updatePersonaCalls = 0;
  int resetPersonaCalls = 0;
  int getRelationshipCalls = 0;
  int resetRelationshipCalls = 0;
  RelationshipMode? updatedRelationshipMode;
  Object? updateRelationshipModeError;
  final List<PersonaUpdate> updates = <PersonaUpdate>[];

  @override
  Future<UserPersona> getPersona() async {
    getPersonaCalls += 1;
    if (getPersonaError != null) throw getPersonaError!;
    return persona;
  }

  @override
  Future<RelationshipStateDto> getRelationship() async {
    getRelationshipCalls += 1;
    if (getRelationshipError != null) throw getRelationshipError!;
    return relationship;
  }

  @override
  Future<RelationshipStateDto> updateRelationshipMode(
    RelationshipMode mode,
  ) async {
    if (updateRelationshipModeError != null) throw updateRelationshipModeError!;
    updatedRelationshipMode = mode;
    relationship = RelationshipStateDto(
      relationshipMode: mode,
      stage: relationship.stage,
      stageLabel: relationship.stageLabel,
      interactionTurns: relationship.interactionTurns,
      activeDays: relationship.activeDays,
      affectionPermission: relationship.affectionPermission,
      schemaVersion: relationship.schemaVersion,
    );
    return relationship;
  }

  @override
  Future<UserPersona> resetPersona() async {
    resetPersonaCalls += 1;
    if (resetPersonaError != null) throw resetPersonaError!;
    persona = nextResetPersona ?? const UserPersona.defaults();
    return persona;
  }

  @override
  Future<RelationshipStateDto> resetRelationship() async {
    resetRelationshipCalls += 1;
    if (resetRelationshipError != null) throw resetRelationshipError!;
    relationship =
        nextResetRelationship ?? const RelationshipStateDto.initial();
    return relationship;
  }

  @override
  Future<UserPersona> updatePersona(PersonaUpdate update) async {
    updatePersonaCalls += 1;
    updates.add(update);
    if (updatePersonaError != null) throw updatePersonaError!;
    persona =
        nextUpdatedPersona ??
        persona.copyWith(
          preferredName: update.preferredName,
          replyStyle: update.replyStyle,
          replyLength: update.replyLength,
          supportMode: update.supportMode,
          proactivity: update.proactivity,
          avoidTopics: update.avoidTopics,
          aboutUser: update.aboutUser,
          relationshipPace: update.relationshipPace,
          affectionStyle: update.affectionStyle,
          enabled: update.enabled,
          isCustomized: true,
          onboardingCompleted: true,
        );
    return persona;
  }
}

class FakeOnboardingCompletionStore extends OnboardingCompletionStore {
  FakeOnboardingCompletionStore() : super(FakePreferencesStore());

  final Set<String> completedUsers = <String>{};
  int markCompletedCalls = 0;
  int clearCalls = 0;

  @override
  Future<void> clear(String userId) async {
    clearCalls += 1;
    completedUsers.remove(userId);
  }

  @override
  Future<bool> isCompleted(String userId) async {
    return completedUsers.contains(userId);
  }

  @override
  Future<void> markCompleted(String userId) async {
    markCompletedCalls += 1;
    completedUsers.add(userId);
  }
}

UserPersona personaFixture({
  String? preferredName = 'Leaf',
  bool onboardingCompleted = true,
}) {
  return const UserPersona.defaults().copyWith(
    preferredName: preferredName,
    isCustomized: preferredName != null,
    onboardingCompleted: onboardingCompleted,
  );
}

RelationshipStateDto relationshipFixture({
  String stage = 'friend',
  String stageLabel = 'Friend',
  int interactionTurns = 12,
}) {
  return RelationshipStateDto(
    stage: stage,
    stageLabel: stageLabel,
    interactionTurns: interactionTurns,
    activeDays: 3,
    affectionPermission: 'contextual',
    schemaVersion: 1,
  );
}
