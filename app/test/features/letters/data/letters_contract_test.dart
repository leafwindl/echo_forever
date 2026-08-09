import 'package:echo_app/features/letters/data/letters_api.dart';
import 'package:echo_app/features/letters/domain/letter.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('defines letters API paths', () {
    expect(LettersApi.listPath, '/letters');
    expect(LettersApi.itemPath, '/letters');
  });

  test('parses list and letter schemas with unread_count', () {
    final response = LetterListResponseDto.fromJson(<String, dynamic>{
      'items': <Map<String, Object?>>[
        <String, Object?>{
          'letter_id': 'letter-1',
          'local_date': '2026-08-04',
          'timezone': 'Asia/Shanghai',
          'status': 'ready',
          'subject': '写给你的信',
          'content': '我们聊过的事，会在这里慢慢沉淀下来。',
          'image_url': 'https://example.com/letter.webp',
          'image_width': 1200,
          'image_height': 900,
          'published_at': '2026-08-04T08:00:00Z',
          'read_at': null,
        },
      ],
      'unread_count': 1,
    });

    final letter = response.items.single;
    expect(response.unreadCount, 1);
    expect(letter.letterId, 'letter-1');
    expect(letter.localDate, '2026-08-04');
    expect(letter.status, LetterStatus.ready);
    expect(letter.status.isUnread, isTrue);
    expect(letter.imageUrl, 'https://example.com/letter.webp');
    expect(letter.imageWidth, 1200);
    expect(letter.imageHeight, 900);
    expect(letter.readAt, isNull);
  });

  test('defaults unknown status without throwing', () {
    final letter = DailyLetter.fromJson(<String, dynamic>{
      'letter_id': 'letter-2',
      'status': 'future-status',
    });

    expect(letter.status, LetterStatus.unknown);
    expect(letter.status.isUnread, isFalse);
    expect(letter.subject, '');
    expect(letter.imageUrl, '');
    expect(letter.imageWidth, isNull);
  });
}
