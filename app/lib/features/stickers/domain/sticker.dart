enum StickerOwnerType {
  echo('echo'),
  user('user'),
  unknown('unknown');

  const StickerOwnerType(this.apiValue);

  final String apiValue;

  static StickerOwnerType fromJson(Object? value) {
    return StickerOwnerType.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => StickerOwnerType.unknown,
    );
  }

  String get label => switch (this) {
    StickerOwnerType.echo => 'Echo',
    StickerOwnerType.user => '我保存的',
    StickerOwnerType.unknown => '未知',
  };
}

enum StickerSource {
  builtin('builtin'),
  generated('generated'),
  uploaded('uploaded'),
  unknown('unknown');

  const StickerSource(this.apiValue);

  final String apiValue;

  static StickerSource fromJson(Object? value) {
    return StickerSource.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => StickerSource.unknown,
    );
  }

  String get label => switch (this) {
    StickerSource.builtin => '内置',
    StickerSource.generated => '生成',
    StickerSource.uploaded => '上传',
    StickerSource.unknown => '未知来源',
  };
}

class StickerItem {
  const StickerItem({
    required this.stickerId,
    required this.ownerType,
    required this.source,
    required this.url,
    required this.contentType,
    required this.description,
    required this.semanticTags,
    required this.status,
    required this.createdAt,
  });

  factory StickerItem.fromJson(Map<String, dynamic> json) {
    return StickerItem(
      stickerId: json['sticker_id'] as String? ?? '',
      ownerType: StickerOwnerType.fromJson(json['owner_type']),
      source: StickerSource.fromJson(json['source']),
      url: json['url'] as String? ?? '',
      contentType: json['content_type'] as String? ?? '',
      description: json['description'] as String? ?? '',
      semanticTags: (json['semantic_tags'] as List? ?? const <Object?>[])
          .map((item) => item.toString())
          .where((item) => item.isNotEmpty)
          .toList(growable: false),
      status: json['status'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
    );
  }

  final String stickerId;
  final StickerOwnerType ownerType;
  final StickerSource source;
  final String url;
  final String contentType;
  final String description;
  final List<String> semanticTags;
  final String status;
  final String createdAt;

  bool get canDelete => ownerType == StickerOwnerType.user;

  Uri? get safeUri {
    final parsed = Uri.tryParse(url);
    if (parsed == null) {
      return null;
    }
    return parsed.isScheme('http') || parsed.isScheme('https') ? parsed : null;
  }
}

class StickerUploadSelection {
  const StickerUploadSelection({
    required this.path,
    required this.name,
    required this.byteLength,
  });

  final String path;
  final String name;
  final int byteLength;
}

class StickerListResult {
  const StickerListResult({required this.items});

  final List<StickerItem> items;
}
