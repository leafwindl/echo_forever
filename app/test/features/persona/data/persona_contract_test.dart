import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/domain/persona.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('defines persona and relationship API paths', () {
    expect(PersonaApi.getPath, '/persona/me');
    expect(PersonaApi.updatePath, '/persona/me');
    expect(PersonaApi.resetPath, '/persona/me/reset');
    expect(PersonaApi.relationshipPath, '/relationship/me');
    expect(PersonaApi.relationshipResetPath, '/relationship/me/reset');
  });

  test('serializes persona update with backend field names', () {
    final update = const PersonaUpdate(
      preferredName: 'Leaf',
      replyStyle: PersonaReplyStyle.concise,
      replyLength: PersonaReplyLength.short,
      supportMode: PersonaSupportMode.advice,
      proactivity: PersonaProactivity.active,
      avoidTopics: <String>['work'],
      aboutUser: 'likes direct answers',
      relationshipPace: RelationshipPace.open,
      affectionStyle: AffectionStyle.expressive,
      enabled: false,
    );

    expect(update.toJson(), <String, Object?>{
      'preferred_name': 'Leaf',
      'reply_style': 'concise',
      'reply_length': 'short',
      'support_mode': 'advice',
      'proactivity': 'active',
      'avoid_topics': <String>['work'],
      'about_user': 'likes direct answers',
      'relationship_pace': 'open',
      'affection_style': 'expressive',
      'enabled': false,
    });
  });

  test('parses persona and relationship backend schemas', () {
    final persona = UserPersonaJson.fromJson(<String, dynamic>{
      'preferred_name': 'Leaf',
      'reply_style': 'lively',
      'reply_length': 'detailed',
      'support_mode': 'comfort',
      'proactivity': 'quiet',
      'avoid_topics': <String>['spoilers'],
      'about_user': 'testing',
      'relationship_pace': 'slow',
      'affection_style': 'restrained',
      'enabled': true,
      'schema_version': 3,
      'is_customized': true,
      'onboarding_completed': true,
      'created_at': '2026-08-04T08:00:00Z',
      'updated_at': '2026-08-04T08:30:00Z',
    });
    final relationship = RelationshipStateDto.fromJson(<String, dynamic>{
      'stage': 'friend',
      'stage_label': 'Friend',
      'interaction_turns': 9,
      'active_days': 4,
      'affection_permission': 'contextual',
      'schema_version': 1,
    });

    expect(persona.preferredName, 'Leaf');
    expect(persona.replyStyle, PersonaReplyStyle.lively);
    expect(persona.replyLength, PersonaReplyLength.detailed);
    expect(persona.supportMode, PersonaSupportMode.comfort);
    expect(persona.proactivity, PersonaProactivity.quiet);
    expect(persona.relationshipPace, RelationshipPace.slow);
    expect(persona.affectionStyle, AffectionStyle.restrained);
    expect(persona.onboardingCompleted, isTrue);
    expect(relationship.stage, 'friend');
    expect(relationship.interactionTurns, 9);
  });

  test('normalizes persona update and validates onboarding name', () {
    final normalized = normalizePersonaUpdate(
      const PersonaUpdate(
        preferredName: '  Leaf  ',
        avoidTopics: <String>[' Work ', 'work', 'Sleep'],
        aboutUser: '  concise  ',
      ),
      requirePreferredName: true,
    );

    expect(normalized.preferredName, 'Leaf');
    expect(normalized.aboutUser, 'concise');
    expect(normalized.avoidTopics, <String>['Work', 'Sleep']);
    expect(
      () => normalizePersonaUpdate(
        const PersonaUpdate(preferredName: '   '),
        requirePreferredName: true,
      ),
      throwsA(isA<FormatException>()),
    );
  });
}
