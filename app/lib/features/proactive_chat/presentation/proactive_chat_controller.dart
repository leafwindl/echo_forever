import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/proactive_chat/data/proactive_chat_providers.dart';
import 'package:echo_app/features/proactive_chat/domain/proactive_chat.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class ProactiveChatState {
  const ProactiveChatState({
    required this.preferences,
    required this.schedules,
    required this.isLoading,
    required this.isSaving,
    this.error,
  });

  const ProactiveChatState.initial()
    : preferences = const ProactiveChatPreferences.defaults(),
      schedules = const <ChatSchedule>[],
      isLoading = false,
      isSaving = false,
      error = null;

  final ProactiveChatPreferences preferences;
  final List<ChatSchedule> schedules;
  final bool isLoading;
  final bool isSaving;
  final AppException? error;

  ProactiveChatState copyWith({
    ProactiveChatPreferences? preferences,
    List<ChatSchedule>? schedules,
    bool? isLoading,
    bool? isSaving,
    AppException? error,
    bool clearError = false,
  }) => ProactiveChatState(
    preferences: preferences ?? this.preferences,
    schedules: schedules ?? this.schedules,
    isLoading: isLoading ?? this.isLoading,
    isSaving: isSaving ?? this.isSaving,
    error: clearError ? null : error ?? this.error,
  );
}

class ProactiveChatController extends AsyncNotifier<ProactiveChatState> {
  @override
  Future<ProactiveChatState> build() async {
    final session = ref.watch(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated != true) {
      return const ProactiveChatState.initial();
    }
    return _load();
  }

  Future<void> refresh() async {
    final current = state.asData?.value ?? const ProactiveChatState.initial();
    state = AsyncData(current.copyWith(isLoading: true, clearError: true));
    try {
      state = AsyncData(await _load());
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isLoading: false, error: _asAppException(error)),
      );
    }
  }

  Future<void> savePreferences(ProactiveChatPreferences preferences) async {
    final current = state.asData?.value ?? const ProactiveChatState.initial();
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      final saved = await ref
          .read(proactiveChatApiProvider)
          .savePreferences(preferences);
      state = AsyncData(
        current.copyWith(preferences: saved, isSaving: false, clearError: true),
      );
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
    }
  }

  Future<void> pause({int? days, bool indefinite = false}) async {
    final current = state.asData?.value;
    if (current == null || current.isSaving) return;
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      final saved = await ref
          .read(proactiveChatApiProvider)
          .pause(days: days, indefinite: indefinite);
      state = AsyncData(
        current.copyWith(preferences: saved, isSaving: false, clearError: true),
      );
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
    }
  }

  Future<void> resume() async {
    final current = state.asData?.value;
    if (current == null || current.isSaving) return;
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      final saved = await ref.read(proactiveChatApiProvider).resume();
      state = AsyncData(
        current.copyWith(preferences: saved, isSaving: false, clearError: true),
      );
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
    }
  }

  Future<void> setScheduleStatus(ChatSchedule schedule, String status) async {
    final current = state.asData?.value;
    if (current == null || current.isSaving) return;
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      await ref
          .read(proactiveChatApiProvider)
          .updateSchedule(schedule.scheduleId, status);
      await refresh();
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
    }
  }

  Future<void> deleteSchedule(ChatSchedule schedule) async {
    final current = state.asData?.value;
    if (current == null || current.isSaving) return;
    state = AsyncData(current.copyWith(isSaving: true, clearError: true));
    try {
      await ref
          .read(proactiveChatApiProvider)
          .deleteSchedule(schedule.scheduleId);
      state = AsyncData(
        current.copyWith(
          schedules: current.schedules
              .where((item) => item.scheduleId != schedule.scheduleId)
              .toList(growable: false),
          isSaving: false,
          clearError: true,
        ),
      );
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isSaving: false, error: _asAppException(error)),
      );
    }
  }

  Future<ProactiveChatState> _load() async {
    final api = ref.read(proactiveChatApiProvider);
    final results = await Future.wait(<Future<Object>>[
      api.getPreferences(),
      api.listSchedules(),
    ]);
    return ProactiveChatState(
      preferences: results[0] as ProactiveChatPreferences,
      schedules: results[1] as List<ChatSchedule>,
      isLoading: false,
      isSaving: false,
    );
  }

  AppException _asAppException(Object error) => error is AppException
      ? error
      : const AppException(kind: AppExceptionKind.unexpected);
}

final proactiveChatControllerProvider =
    AsyncNotifierProvider<ProactiveChatController, ProactiveChatState>(
      ProactiveChatController.new,
    );
