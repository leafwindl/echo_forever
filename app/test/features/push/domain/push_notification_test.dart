import 'package:echo_app/features/push/domain/push_notification.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PushNotification', () {
    test('parses a versioned whitelisted route', () {
      final notification = PushNotification.fromData(<String, dynamic>{
        'schema_version': '1',
        'type': 'letter_ready',
        'route': 'letters',
        'entity_id': 'letter_01J',
        'notification_id': 'notice_01J',
      });

      expect(notification, isNotNull);
      expect(notification!.appLocation, '/letters');
      expect(notification.navigationLocation, '/letters?entity_id=letter_01J');
      expect(notification.entityId, 'letter_01J');
    });

    test('rejects unsupported schema and arbitrary routes', () {
      expect(
        PushNotification.fromData(<String, dynamic>{
          'schema_version': '2',
          'type': 'letter_ready',
          'route': 'letters',
          'notification_id': 'notice_01J',
        }),
        isNull,
      );
      expect(
        PushNotification.fromData(<String, dynamic>{
          'schema_version': '1',
          'type': 'open_url',
          'route': 'https://example.com',
          'notification_id': 'notice_01K',
        }),
        isNull,
      );
    });

    test('maps chat payloads to the guarded chat route', () {
      final notification = PushNotification.fromData(<String, dynamic>{
        'schema_version': '1',
        'type': 'chat_reply',
        'route': 'chat',
        'notification_id': 'notice_chat_01',
      });

      expect(notification, isNotNull);
      expect(notification!.appLocation, '/chat');
    });

    test('rejects empty required fields', () {
      expect(
        PushNotification.fromData(<String, dynamic>{
          'schema_version': '1',
          'type': '',
          'route': 'chat',
          'notification_id': 'notice_empty_type',
        }),
        isNull,
      );
    });
  });
}
