import 'package:echo_app/features/memory/data/memory_repository.dart';
import 'package:echo_app/features/memory/domain/memory.dart';

class FakeMemoryRepository implements MemoryRepository {
  FakeMemoryRepository({
    List<MemoryRecord>? activeMemories,
    List<MemoryRecord>? deletedMemories,
  }) : activeMemories = List<MemoryRecord>.of(
         activeMemories ?? <MemoryRecord>[memoryFixture()],
       ),
       deletedMemories = List<MemoryRecord>.of(
         deletedMemories ?? <MemoryRecord>[],
       );

  List<MemoryRecord> activeMemories;
  List<MemoryRecord> deletedMemories;
  Object? listError;
  Object? deleteError;
  Object? clearError;
  Future<MemoryDeleteResult> Function(String memoryId)? onDeleteMemory;
  int listCalls = 0;
  int deleteCalls = 0;
  int clearCalls = 0;
  final List<MemoryStatus> listedStatuses = <MemoryStatus>[];
  final List<int> listedLimits = <int>[];
  final List<String> deletedIds = <String>[];

  @override
  Future<MemoryClearResult> clearMemories() async {
    clearCalls += 1;
    if (clearError != null) throw clearError!;
    final cleared = activeMemories.length;
    activeMemories = <MemoryRecord>[];
    return MemoryClearResult(clearedCount: cleared);
  }

  @override
  Future<MemoryDeleteResult> deleteMemory(String memoryId) async {
    deleteCalls += 1;
    deletedIds.add(memoryId);
    if (deleteError != null) throw deleteError!;
    if (onDeleteMemory != null) {
      return onDeleteMemory!(memoryId);
    }
    final index = activeMemories.indexWhere(
      (memory) => memory.memoryId == memoryId,
    );
    if (index != -1) {
      final memory = activeMemories.removeAt(index);
      deletedMemories.add(
        MemoryRecord(
          memoryId: memory.memoryId,
          memoryType: memory.memoryType,
          content: memory.content,
          confidence: memory.confidence,
          importance: memory.importance,
          status: MemoryStatus.deleted,
          sourceMessageId: memory.sourceMessageId,
          createdAt: memory.createdAt,
          updatedAt: memory.updatedAt,
          expiresAt: memory.expiresAt,
        ),
      );
    }
    return MemoryDeleteResult(memoryId: memoryId, status: MemoryStatus.deleted);
  }

  @override
  Future<MemoryListResult> listMemories({
    required MemoryStatus status,
    required int limit,
  }) async {
    listCalls += 1;
    listedStatuses.add(status);
    listedLimits.add(limit);
    if (listError != null) throw listError!;
    final source = status == MemoryStatus.deleted
        ? deletedMemories
        : activeMemories;
    final memories = source.take(limit).toList(growable: false);
    return MemoryListResult(memories: memories, count: source.length);
  }
}

MemoryRecord memoryFixture({
  String memoryId = 'mem-1',
  String content = 'favorite color is green',
  MemoryStatus status = MemoryStatus.active,
}) {
  return MemoryRecord(
    memoryId: memoryId,
    memoryType: MemoryType.preference,
    content: content,
    confidence: 0.92,
    importance: 4,
    status: status,
    sourceMessageId: 7,
    createdAt: '2026-08-04T08:00:00Z',
    updatedAt: '2026-08-04T08:30:00Z',
  );
}
