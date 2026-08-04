import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/letters/domain/letter.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class LettersState {
  const LettersState({
    required this.letters,
    required this.unreadCount,
    required this.isLoading,
    this.selected,
    this.openingId,
    this.readingId,
    this.error,
  });

  const LettersState.loading()
    : letters = const <DailyLetter>[],
      unreadCount = 0,
      isLoading = true,
      selected = null,
      openingId = null,
      readingId = null,
      error = null;

  final List<DailyLetter> letters;
  final int unreadCount;
  final bool isLoading;
  final DailyLetter? selected;
  final String? openingId;
  final String? readingId;
  final AppException? error;

  bool get isBusy => isLoading || openingId != null || readingId != null;

  LettersState copyWith({
    List<DailyLetter>? letters,
    int? unreadCount,
    bool? isLoading,
    DailyLetter? selected,
    bool clearSelected = false,
    String? openingId,
    bool clearOpeningId = false,
    String? readingId,
    bool clearReadingId = false,
    AppException? error,
    bool clearError = false,
  }) {
    return LettersState(
      letters: letters ?? this.letters,
      unreadCount: unreadCount ?? this.unreadCount,
      isLoading: isLoading ?? this.isLoading,
      selected: clearSelected ? null : selected ?? this.selected,
      openingId: clearOpeningId ? null : openingId ?? this.openingId,
      readingId: clearReadingId ? null : readingId ?? this.readingId,
      error: clearError ? null : error ?? this.error,
    );
  }
}

class LettersController extends AsyncNotifier<LettersState> {
  static const int defaultLimit = 50;

  @override
  Future<LettersState> build() async {
    final session = ref.watch(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated != true) {
      return const LettersState(
        letters: <DailyLetter>[],
        unreadCount: 0,
        isLoading: false,
      );
    }
    try {
      return await _fetch();
    } on Object catch (error) {
      return _defaultState().copyWith(error: _asAppException(error));
    }
  }

  Future<LettersState?> refresh() async {
    final current = _currentState() ?? _defaultState();
    state = AsyncData(current.copyWith(isLoading: true, clearError: true));
    try {
      final next = await _fetch(previous: current);
      state = AsyncData(next);
      return next;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isLoading: false, error: _asAppException(error)),
      );
      return null;
    }
  }

  Future<bool> openLetter(String letterId) async {
    final current = _currentState();
    if (current == null || current.isLoading) {
      return false;
    }
    final fallback = _findLetter(current.letters, letterId);
    if (fallback == null) {
      return false;
    }
    state = AsyncData(
      current.copyWith(
        selected: fallback,
        openingId: letterId,
        clearReadingId: true,
        clearError: true,
      ),
    );

    try {
      final detail = await ref
          .read(lettersRepositoryProvider)
          .getLetter(letterId);
      final withDetail = _replaceLetter(
        (_currentState() ?? current).letters,
        detail,
      );
      var next = (_currentState() ?? current).copyWith(
        letters: withDetail,
        unreadCount: _countUnread(withDetail),
        selected: detail,
        clearOpeningId: true,
        clearError: true,
      );
      state = AsyncData(next);
      if (detail.status.isUnread) {
        final read = await _markRead(detail.letterId, previous: next);
        next = read ?? next;
      }
      return true;
    } on Object catch (error) {
      state = AsyncData(
        (_currentState() ?? current).copyWith(
          clearOpeningId: true,
          clearReadingId: true,
          error: _asAppException(error),
        ),
      );
      return false;
    }
  }

  Future<bool> markSelectedRead() async {
    final current = _currentState();
    final selected = current?.selected;
    if (current == null || selected == null || !selected.status.isUnread) {
      return false;
    }
    return await _markRead(selected.letterId, previous: current) != null;
  }

  void closeLetter() {
    final current = _currentState();
    if (current != null) {
      state = AsyncData(current.copyWith(clearSelected: true));
    }
  }

  void clearError() {
    final current = _currentState();
    if (current != null) {
      state = AsyncData(current.copyWith(clearError: true));
    }
  }

  Future<LettersState?> _markRead(
    String letterId, {
    required LettersState previous,
  }) async {
    if (previous.readingId != null) {
      return null;
    }
    state = AsyncData(previous.copyWith(readingId: letterId, clearError: true));
    try {
      final updated = await ref
          .read(lettersRepositoryProvider)
          .markRead(letterId);
      final letters = _replaceLetter(
        (_currentState() ?? previous).letters,
        updated,
      );
      final next = (_currentState() ?? previous).copyWith(
        letters: letters,
        unreadCount: _countUnread(letters),
        selected: updated,
        clearReadingId: true,
        clearError: true,
      );
      state = AsyncData(next);
      return next;
    } on Object catch (error) {
      final next = (_currentState() ?? previous).copyWith(
        clearReadingId: true,
        error: _asAppException(error),
      );
      state = AsyncData(next);
      return null;
    }
  }

  Future<LettersState> _fetch({LettersState? previous}) async {
    final response = await ref
        .read(lettersRepositoryProvider)
        .listLetters(limit: defaultLimit);
    return (previous ?? _defaultState()).copyWith(
      letters: response.items,
      unreadCount: response.unreadCount,
      isLoading: false,
      clearOpeningId: true,
      clearReadingId: true,
      clearError: true,
    );
  }

  LettersState _defaultState() {
    return const LettersState(
      letters: <DailyLetter>[],
      unreadCount: 0,
      isLoading: false,
    );
  }

  LettersState? _currentState() => state.asData?.value;

  static DailyLetter? _findLetter(List<DailyLetter> letters, String letterId) {
    for (final letter in letters) {
      if (letter.letterId == letterId) {
        return letter;
      }
    }
    return null;
  }

  static List<DailyLetter> _replaceLetter(
    List<DailyLetter> letters,
    DailyLetter updated,
  ) {
    var replaced = false;
    final next = letters
        .map((letter) {
          if (letter.letterId != updated.letterId) {
            return letter;
          }
          replaced = true;
          return updated;
        })
        .toList(growable: false);
    return replaced ? next : <DailyLetter>[updated, ...letters];
  }

  static int _countUnread(List<DailyLetter> letters) {
    return letters.where((letter) => letter.status.isUnread).length;
  }

  static AppException _asAppException(Object error) {
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

final lettersControllerProvider =
    AsyncNotifierProvider<LettersController, LettersState>(
      LettersController.new,
    );

final lettersUnreadCountProvider = Provider<int>((ref) {
  return ref.watch(
    lettersControllerProvider.select(
      (state) => state.asData?.value.unreadCount ?? 0,
    ),
  );
});
