import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/storage/onboarding_completion_store.dart';
import 'package:echo_app/features/persona/data/persona_api.dart';
import 'package:echo_app/features/persona/domain/persona.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class PersonaState {
  const PersonaState({
    required this.persona,
    required this.isLoading,
    required this.isSaving,
    this.error,
  });

  const PersonaState.loading()
    : persona = const UserPersona.defaults(),
      isLoading = true,
      isSaving = false,
      error = null;

  final UserPersona persona;
  final bool isLoading;
  final bool isSaving;
  final AppException? error;

  bool get onboardingCompleted => persona.onboardingCompleted;
  bool get isBusy => isLoading || isSaving;
  bool get hasError => error != null;

  PersonaState copyWith({
    UserPersona? persona,
    bool? isLoading,
    bool? isSaving,
    AppException? error,
    bool clearError = false,
  }) {
    return PersonaState(
      persona: persona ?? this.persona,
      isLoading: isLoading ?? this.isLoading,
      isSaving: isSaving ?? this.isSaving,
      error: clearError ? null : error ?? this.error,
    );
  }
}

class PersonaController extends AsyncNotifier<PersonaState> {
  @override
  Future<PersonaState> build() async {
    final session = ref.watch(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated != true) {
      return const PersonaState(
        persona: UserPersona.defaults(),
        isLoading: false,
        isSaving: false,
      );
    }
    final userId = session!.userId!;
    final localOnboardingCompleted = await ref
        .read(onboardingCompletionStoreProvider)
        .isCompleted(userId);
    try {
      final persona = await ref.read(personaRepositoryProvider).getPersona();
      final merged = _mergeOnboardingState(
        persona,
        localOnboardingCompleted: localOnboardingCompleted,
      );
      await _persistOnboardingCompleted(merged);
      return PersonaState(persona: merged, isLoading: false, isSaving: false);
    } on Object catch (error) {
      return PersonaState(
        persona: UserPersona.defaults().copyWith(
          onboardingCompleted: localOnboardingCompleted,
        ),
        isLoading: false,
        isSaving: false,
        error: _asAppException(error),
      );
    }
  }

  Future<UserPersona?> refresh() async {
    final session = ref.read(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated != true) {
      state = const AsyncData(
        PersonaState(
          persona: UserPersona.defaults(),
          isLoading: false,
          isSaving: false,
        ),
      );
      return null;
    }
    final current = _currentState() ?? _defaultState();
    state = AsyncData(current.copyWith(isLoading: true, clearError: true));
    try {
      final persona = await ref.read(personaRepositoryProvider).getPersona();
      final merged = _mergeOnboardingState(
        persona,
        localOnboardingCompleted: await ref
            .read(onboardingCompletionStoreProvider)
            .isCompleted(session!.userId!),
      );
      await _persistOnboardingCompleted(merged);
      final next = current.copyWith(
        persona: merged,
        isLoading: false,
        clearError: true,
      );
      state = AsyncData(next);
      return merged;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isLoading: false, error: _asAppException(error)),
      );
      return null;
    }
  }

  Future<UserPersona?> updatePersona(PersonaUpdate update) async {
    final current = _currentState();
    if (current == null || current.isBusy) {
      return null;
    }
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      final normalized = normalizePersonaUpdate(
        update,
        requirePreferredName: !current.persona.onboardingCompleted,
      );
      final persona = await ref
          .read(personaRepositoryProvider)
          .updatePersona(normalized);
      await _persistOnboardingCompleted(persona);
      await _syncCurrentPersona(persona);
      return persona;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
      return null;
    }
  }

  Future<UserPersona?> resetPersona() async {
    final current = _currentState();
    if (current == null || current.isBusy) {
      return null;
    }
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      final persona = await ref.read(personaRepositoryProvider).resetPersona();
      await _syncCurrentPersona(persona);
      return persona;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
      return null;
    }
  }

  Future<RelationshipStateDto?> resetRelationship() async {
    final current = _currentState();
    if (current == null || current.isBusy) {
      return null;
    }
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      final relationship = await ref
          .read(personaRepositoryProvider)
          .resetRelationship();
      ref.invalidate(relationshipStateProvider);
      return relationship;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
      return null;
    } finally {
      final currentState = _currentState();
      if (currentState != null && currentState.isSaving) {
        state = AsyncData(currentState.copyWith(isSaving: false));
      }
    }
  }

  Future<void> _persistOnboardingCompleted(UserPersona persona) async {
    final session = ref.read(sessionControllerProvider).asData?.value;
    if (session?.userId == null) {
      return;
    }
    if (persona.onboardingCompleted) {
      await ref
          .read(onboardingCompletionStoreProvider)
          .markCompleted(session!.userId!);
    }
  }

  Future<void> _syncCurrentPersona(UserPersona persona) async {
    final current = _currentState() ?? _defaultState();
    final next = current.copyWith(
      persona: persona,
      isLoading: false,
      isSaving: false,
      clearError: true,
    );
    state = AsyncData(next);
  }

  PersonaState? _currentState() => state.asData?.value;

  PersonaState _defaultState() {
    return const PersonaState(
      persona: UserPersona.defaults(),
      isLoading: false,
      isSaving: false,
    );
  }

  UserPersona _mergeOnboardingState(
    UserPersona persona, {
    required bool localOnboardingCompleted,
  }) {
    if (localOnboardingCompleted && !persona.onboardingCompleted) {
      return persona.copyWith(onboardingCompleted: true);
    }
    return persona;
  }

  AppException _asAppException(Object error) {
    if (error is AppException) {
      return error;
    }
    if (error is FormatException) {
      return AppException(
        kind: AppExceptionKind.badRequest,
        detail: error.message,
      );
    }
    return const AppException(kind: AppExceptionKind.unexpected);
  }
}

final personaControllerProvider =
    AsyncNotifierProvider<PersonaController, PersonaState>(
      PersonaController.new,
    );

final relationshipStateProvider =
    FutureProvider.autoDispose<RelationshipStateDto>((ref) async {
      final session = ref.watch(sessionControllerProvider).asData?.value;
      if (session?.isAuthenticated != true) {
        return const RelationshipStateDto.initial();
      }
      return ref.read(personaRepositoryProvider).getRelationship();
    });
