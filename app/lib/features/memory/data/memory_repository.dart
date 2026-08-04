import 'package:echo_app/features/memory/data/memory_api.dart';
import 'package:echo_app/features/memory/domain/memory.dart';

abstract interface class MemoryRepository {
  Future<MemoryListResult> listMemories({
    required MemoryStatus status,
    required int limit,
  });

  Future<MemoryDeleteResult> deleteMemory(String memoryId);

  Future<MemoryClearResult> clearMemories();
}

class MemoryRepositoryImpl implements MemoryRepository {
  const MemoryRepositoryImpl(this._api);

  final MemoryApi _api;

  @override
  Future<MemoryListResult> listMemories({
    required MemoryStatus status,
    required int limit,
  }) async {
    final response = await _api.listMemories(
      status: status.apiValue,
      limit: limit,
    );
    return MemoryListResult(memories: response.memories, count: response.count);
  }

  @override
  Future<MemoryDeleteResult> deleteMemory(String memoryId) async {
    final response = await _api.deleteMemory(memoryId);
    return MemoryDeleteResult(
      memoryId: response.memoryId,
      status: response.status,
    );
  }

  @override
  Future<MemoryClearResult> clearMemories() async {
    final response = await _api.clearMemories();
    return MemoryClearResult(clearedCount: response.clearedCount);
  }
}
