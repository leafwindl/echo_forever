enum LetterStatus {
  ready('ready'),
  read('read'),
  unknown('unknown');

  const LetterStatus(this.apiValue);

  final String apiValue;

  static LetterStatus fromJson(Object? value) {
    return LetterStatus.values.firstWhere(
      (item) => item.apiValue == value,
      orElse: () => LetterStatus.unknown,
    );
  }

  bool get isUnread => this == LetterStatus.ready;

  String get label => switch (this) {
    LetterStatus.ready => '未读',
    LetterStatus.read => '已读',
    LetterStatus.unknown => '未知',
  };
}

class DailyLetter {
  const DailyLetter({
    required this.letterId,
    required this.localDate,
    required this.timezone,
    required this.status,
    required this.subject,
    required this.content,
    this.imageUrl = '',
    this.imageWidth,
    this.imageHeight,
    this.publishedAt,
    this.readAt,
  });

  factory DailyLetter.fromJson(Map<String, dynamic> json) {
    return DailyLetter(
      letterId: json['letter_id'] as String? ?? '',
      localDate: json['local_date'] as String? ?? '',
      timezone: json['timezone'] as String? ?? '',
      status: LetterStatus.fromJson(json['status']),
      subject: json['subject'] as String? ?? '',
      content: json['content'] as String? ?? '',
      imageUrl: json['image_url'] as String? ?? '',
      imageWidth: json['image_width'] as int?,
      imageHeight: json['image_height'] as int?,
      publishedAt: json['published_at'] as String?,
      readAt: json['read_at'] as String?,
    );
  }

  final String letterId;
  final String localDate;
  final String timezone;
  final LetterStatus status;
  final String subject;
  final String content;
  final String imageUrl;
  final int? imageWidth;
  final int? imageHeight;
  final String? publishedAt;
  final String? readAt;
}

class LetterListResult {
  const LetterListResult({required this.items, required this.unreadCount});

  final List<DailyLetter> items;
  final int unreadCount;
}
