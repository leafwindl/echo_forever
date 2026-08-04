enum MemoryStatus {
  active('active'),
  inactive('inactive'),
  deleted('deleted'),
  unknown('unknown');

  const MemoryStatus(this.apiValue);

  final String apiValue;

  static MemoryStatus fromJson(Object? value) {
    return MemoryStatus.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => MemoryStatus.unknown,
    );
  }

  String get label => switch (this) {
    MemoryStatus.active => '有效',
    MemoryStatus.inactive => '停用',
    MemoryStatus.deleted => '已删除',
    MemoryStatus.unknown => '未知',
  };
}

enum MemoryType {
  profile('profile'),
  preference('preference'),
  relationship('relationship'),
  goal('goal'),
  event('event'),
  boundary('boundary'),
  unknown('unknown');

  const MemoryType(this.apiValue);

  final String apiValue;

  static MemoryType fromJson(Object? value) {
    return MemoryType.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => MemoryType.unknown,
    );
  }

  String get label => switch (this) {
    MemoryType.profile => '资料',
    MemoryType.preference => '偏好',
    MemoryType.relationship => '关系',
    MemoryType.goal => '目标',
    MemoryType.event => '事件',
    MemoryType.boundary => '边界',
    MemoryType.unknown => '未知',
  };
}

class MemoryRecord {
  const MemoryRecord({
    required this.memoryId,
    required this.memoryType,
    required this.content,
    required this.confidence,
    required this.importance,
    required this.status,
    this.sourceMessageId,
    this.createdAt,
    this.updatedAt,
    this.expiresAt,
  });

  factory MemoryRecord.fromJson(Map<String, dynamic> json) {
    return MemoryRecord(
      memoryId: json['memory_id'] as String? ?? '',
      memoryType: MemoryType.fromJson(json['memory_type']),
      content: json['content'] as String? ?? '',
      sourceMessageId: json['source_message_id'] as int?,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      importance: (json['importance'] as num?)?.toInt() ?? 0,
      status: MemoryStatus.fromJson(json['status']),
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
      expiresAt: json['expires_at'] as String?,
    );
  }

  final String memoryId;
  final MemoryType memoryType;
  final String content;
  final int? sourceMessageId;
  final double confidence;
  final int importance;
  final MemoryStatus status;
  final String? createdAt;
  final String? updatedAt;
  final String? expiresAt;
}

class MemoryListResult {
  const MemoryListResult({
    required this.memories,
    required this.count,
  });

  final List<MemoryRecord> memories;
  final int count;
}

class MemoryDeleteResult {
  const MemoryDeleteResult({
    required this.memoryId,
    required this.status,
  });

  final String memoryId;
  final MemoryStatus status;
}

class MemoryClearResult {
  const MemoryClearResult({
    required this.clearedCount,
  });

  final int clearedCount;
}
