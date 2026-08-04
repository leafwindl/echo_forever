import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/memory/domain/memory.dart';

class MemoryApi {
  const MemoryApi(this._client);

  final DioClient _client;

  static const listPath = '/memory/list';
  static const deletePath = '/memory';
  static const clearPath = '/memory/clear';

  Future<MemoryListResponseDto> listMemories({
    required String status,
    int limit = 100,
  }) async {
    final response = await _client.get<Map<String, dynamic>>(
      listPath,
      queryParameters: <String, dynamic>{
        'status': status,
        'limit': limit,
      },
    );
    return MemoryListResponseDto.fromJson(response.data!);
  }

  Future<MemoryDeleteResponseDto> deleteMemory(String memoryId) async {
    final response = await _client.delete<Map<String, dynamic>>(
      '$deletePath/$memoryId',
    );
    return MemoryDeleteResponseDto.fromJson(response.data!);
  }

  Future<MemoryClearResponseDto> clearMemories() async {
    final response = await _client.post<Map<String, dynamic>>(clearPath);
    return MemoryClearResponseDto.fromJson(response.data!);
  }
}

class MemoryListResponseDto {
  const MemoryListResponseDto({
    required this.memories,
    required this.count,
  });

  factory MemoryListResponseDto.fromJson(Map<String, dynamic> json) {
    return MemoryListResponseDto(
      memories: (json['memories'] as List? ?? const <Object?>[])
          .whereType<Map<String, dynamic>>()
          .map(MemoryRecord.fromJson)
          .toList(growable: false),
      count: json['count'] as int? ?? 0,
    );
  }

  final List<MemoryRecord> memories;
  final int count;
}

class MemoryDeleteResponseDto {
  const MemoryDeleteResponseDto({
    required this.memoryId,
    required this.status,
  });

  factory MemoryDeleteResponseDto.fromJson(Map<String, dynamic> json) {
    return MemoryDeleteResponseDto(
      memoryId: json['memory_id'] as String? ?? '',
      status: MemoryStatus.fromJson(json['status']),
    );
  }

  final String memoryId;
  final MemoryStatus status;
}

class MemoryClearResponseDto {
  const MemoryClearResponseDto({
    required this.clearedCount,
  });

  factory MemoryClearResponseDto.fromJson(Map<String, dynamic> json) {
    return MemoryClearResponseDto(
      clearedCount: json['cleared_count'] as int? ?? 0,
    );
  }

  final int clearedCount;
}
