import 'package:echo_app/features/presence/domain/presence.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PresenceSnapshot', () {
    test('parses state, budget and thoughts', () {
      final snapshot = PresenceSnapshot.fromJson(<String, dynamic>{
        'status': 'idle',
        'enabled': true,
        'thoughts_used': 2,
        'daily_thought_budget': 8,
        'last_thought_at': '2026-11-02T11:34:27.831980Z',
        'thoughts': <Map<String, dynamic>>[
          <String, dynamic>{
            'thought_id': 'thought_1',
            'text': '她今天好像有点累',
            'salience': 0.6,
            'shareable': false,
            'action_intent': '',
            'created_at': '2026-11-02T11:34:27.831980Z',
          },
        ],
      });

      expect(snapshot.statusLabel, '闲着');
      expect(snapshot.thoughtsUsed, 2);
      expect(snapshot.dailyThoughtBudget, 8);
      expect(snapshot.hasThoughts, isTrue);
      expect(snapshot.thoughts.single.text, '她今天好像有点累');
      expect(snapshot.thoughts.single.createdAt, isNotNull);
    });

    test('labels sleeping state and handles empty thoughts', () {
      final snapshot = PresenceSnapshot.fromJson(<String, dynamic>{
        'status': 'sleeping',
        'enabled': true,
        'thoughts_used': 0,
        'daily_thought_budget': 8,
        'thoughts': <Object?>[],
      });

      expect(snapshot.statusLabel, '安静着');
      expect(snapshot.hasThoughts, isFalse);
    });
  });
}
