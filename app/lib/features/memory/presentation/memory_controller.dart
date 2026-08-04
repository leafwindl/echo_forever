import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/memory/domain/memory.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

enum MemoryTab {
  active('active', '有效', Icons.inbox_rounded),
  deleted('deleted', '已删除', Icons.delete_outline_rounded);

  const MemoryTab(this.apiValue, this.label, this.icon);

  final String apiValue;
  final String label;
  final IconData icon;
}

class MemoryState {
  const MemoryState({
    required this.tab,
    required this.memories,
    required this.count,
    required this.isLoading,
    required this.isClearing,
    this.deletingId,
    this.error,
  });

  const MemoryState.loading({this.tab = MemoryTab.active})
    : memories = const <MemoryRecord>[],
      count = 0,
      isLoading = true,
      isClearing = false,
      deletingId = null,
      error = null;

  final MemoryTab tab;
  final List<MemoryRecord> memories;
  final int count;
  final bool isLoading;
  final bool isClearing;
  final String? deletingId;
  final AppException? error;

  bool get isBusy => isLoading || isClearing || deletingId != null;

  bool get canClear =>
      tab == MemoryTab.active && memories.isNotEmpty && !isBusy;

  MemoryState copyWith({
    MemoryTab? tab,
    List<MemoryRecord>? memories,
    bool clearMemories = false,
    int? count,
    bool? isLoading,
    bool? isClearing,
    String? deletingId,
    bool clearDeletingId = false,
    AppException? error,
    bool clearError = false,
  }) {
    return MemoryState(
      tab: tab ?? this.tab,
      memories: clearMemories
          ? const <MemoryRecord>[]
          : memories ?? this.memories,
      count: count ?? this.count,
      isLoading: isLoading ?? this.isLoading,
      isClearing: isClearing ?? this.isClearing,
      deletingId: clearDeletingId ? null : deletingId ?? this.deletingId,
      error: clearError ? null : error ?? this.error,
    );
  }
}

class MemoryController extends AsyncNotifier<MemoryState> {
  static const int _defaultLimit = 100;

  @override
  Future<MemoryState> build() async {
    final session = ref.watch(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated != true) {
      return const MemoryState(
        tab: MemoryTab.active,
        memories: <MemoryRecord>[],
        count: 0,
        isLoading: false,
        isClearing: false,
      );
    }
    try {
      return await _fetchTab(MemoryTab.active);
    } on Object catch (error) {
      return _defaultState().copyWith(error: _asAppException(error));
    }
  }

  Future<MemoryState?> switchTab(MemoryTab tab) async {
    final current = _currentState() ?? _defaultState();
    if (current.tab == tab && !current.isLoading) {
      return current;
    }
    state = AsyncData(
      current.copyWith(
        tab: tab,
        isLoading: true,
        clearError: true,
        clearMemories: true,
        clearDeletingId: true,
      ),
    );
    try {
      final next = await _fetchTab(tab, previous: _currentState());
      state = AsyncData(next);
      return next;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(
          tab: tab,
          isLoading: false,
          error: _asAppException(error),
        ),
      );
      return null;
    }
  }

  Future<MemoryState?> refresh() async {
    final current = _currentState() ?? _defaultState();
    state = AsyncData(current.copyWith(isLoading: true, clearError: true));
    try {
      final next = await _fetchTab(current.tab, previous: current);
      state = AsyncData(next);
      return next;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isLoading: false, error: _asAppException(error)),
      );
      return null;
    }
  }

  Future<bool> deleteMemory(String memoryId) async {
    final current = _currentState();
    if (current == null || current.isBusy) {
      return false;
    }
    state = AsyncData(current.copyWith(deletingId: memoryId, clearError: true));
    try {
      await ref.read(memoryRepositoryProvider).deleteMemory(memoryId);
      final next = await _fetchTab(current.tab, previous: current);
      state = AsyncData(next);
      return true;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(clearDeletingId: true, error: _asAppException(error)),
      );
      return false;
    }
  }

  Future<int?> clearMemories() async {
    final current = _currentState();
    if (current == null || !current.canClear) {
      return null;
    }
    state = AsyncData(current.copyWith(isClearing: true, clearError: true));
    try {
      final result = await ref.read(memoryRepositoryProvider).clearMemories();
      final next = await _fetchTab(MemoryTab.active, previous: current);
      state = AsyncData(next);
      return result.clearedCount;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isClearing: false, error: _asAppException(error)),
      );
      return null;
    }
  }

  Future<MemoryState> _fetchTab(MemoryTab tab, {MemoryState? previous}) async {
    final response = await ref
        .read(memoryRepositoryProvider)
        .listMemories(
          status: tab == MemoryTab.active
              ? MemoryStatus.active
              : MemoryStatus.deleted,
          limit: _defaultLimit,
        );
    return (previous ?? _defaultState()).copyWith(
      tab: tab,
      memories: response.memories,
      count: response.count,
      isLoading: false,
      isClearing: false,
      clearDeletingId: true,
      clearError: true,
    );
  }

  MemoryState _defaultState() {
    return const MemoryState(
      tab: MemoryTab.active,
      memories: <MemoryRecord>[],
      count: 0,
      isLoading: false,
      isClearing: false,
    );
  }

  MemoryState? _currentState() => state.asData?.value;

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

final memoryControllerProvider =
    AsyncNotifierProvider<MemoryController, MemoryState>(MemoryController.new);
