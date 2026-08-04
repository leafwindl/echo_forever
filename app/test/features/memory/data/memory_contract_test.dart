import 'package:echo_app/features/memory/data/memory_api.dart';
import 'package:echo_app/features/memory/domain/memory.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('defines memory API paths', () {
    expect(MemoryApi.listPath, '/memory/list');
    expect(MemoryApi.deletePath, '/memory');
    expect(MemoryApi.clearPath, '/memory/clear');
  });

  test('parses memory list, delete and clear schemas', () {
    final list = MemoryListResponseDto.fromJson(<String, dynamic>{
      'memories': <Map<String, Object?>>[
        <String, Object?>{
          'memory_id': 'mem-1',
          'memory_type': 'preference',
          'content': 'favorite color is green',
          'source_message_id': 7,
          'confidence': 0.92,
          'importance': 4,
          'status': 'active',
          'created_at': '2026-08-04T08:00:00Z',
          'updated_at': '2026-08-04T08:30:00Z',
        },
      ],
      'count': 1,
    });
    final deleted = MemoryDeleteResponseDto.fromJson(<String, dynamic>{
      'memory_id': 'mem-1',
      'status': 'deleted',
    });
    final cleared = MemoryClearResponseDto.fromJson(<String, dynamic>{
      'cleared_count': 3,
    });

    expect(list.count, 1);
    expect(list.memories.single.memoryId, 'mem-1');
    expect(list.memories.single.memoryType, MemoryType.preference);
    expect(list.memories.single.status, MemoryStatus.active);
    expect(list.memories.single.confidence, 0.92);
    expect(deleted.memoryId, 'mem-1');
    expect(deleted.status, MemoryStatus.deleted);
    expect(cleared.clearedCount, 3);
  });

  test('defaults unknown enum values without throwing', () {
    final memory = MemoryRecord.fromJson(<String, dynamic>{
      'memory_id': 'mem-2',
      'memory_type': 'future-kind',
      'content': 'unknown shape',
      'status': 'future-status',
    });

    expect(memory.memoryType, MemoryType.unknown);
    expect(memory.status, MemoryStatus.unknown);
    expect(memory.importance, 0);
    expect(memory.confidence, 0);
  });
}
