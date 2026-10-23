import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/domain/persona.dart';

abstract interface class PersonaRepository {
  Future<UserPersona> getPersona();
  Future<UserPersona> resetPersona();
  Future<UserPersona> updatePersona(PersonaUpdate update);
  Future<RelationshipStateDto> getRelationship();
  Future<RelationshipStateDto> resetRelationship();
  Future<RelationshipStateDto> updateRelationshipMode(RelationshipMode mode);
}

class PersonaRepositoryImpl implements PersonaRepository {
  const PersonaRepositoryImpl(this._api);

  final PersonaApi _api;

  @override
  Future<UserPersona> getPersona() => _api.getPersona();

  @override
  Future<UserPersona> resetPersona() => _api.resetPersona();

  @override
  Future<UserPersona> updatePersona(PersonaUpdate update) =>
      _api.updatePersona(update);

  @override
  Future<RelationshipStateDto> getRelationship() => _api.getRelationship();

  @override
  Future<RelationshipStateDto> resetRelationship() => _api.resetRelationship();

  @override
  Future<RelationshipStateDto> updateRelationshipMode(RelationshipMode mode) =>
      _api.updateRelationshipMode(mode);
}
