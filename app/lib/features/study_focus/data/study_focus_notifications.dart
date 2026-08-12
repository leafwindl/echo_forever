import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tz;
import 'package:timezone/timezone.dart' as timezone;

class StudyFocusNotificationService {
  static const _notificationId = 31809;
  static const _channelId = 'echo_study_focus';
  static const _channelName = '学习结束提醒';

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized ||
        kIsWeb ||
        defaultTargetPlatform != TargetPlatform.android) {
      return;
    }
    tz.initializeTimeZones();
    const settings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    );
    await _plugin.initialize(settings: settings);
    final android = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    await android?.createNotificationChannel(
      AndroidNotificationChannel(
        _channelId,
        _channelName,
        description: '一起学习完成后的本地震动提醒',
        importance: Importance.high,
        playSound: false,
        enableVibration: true,
        vibrationPattern: Int64List.fromList(<int>[0, 500, 220, 500]),
      ),
    );
    await android?.requestNotificationsPermission();
    await android?.requestExactAlarmsPermission();
    _initialized = true;
  }

  Future<void> schedule(DateTime endAt) async {
    try {
      await initialize();
    } on Object {
      return;
    }
    if (!_initialized) return;
    final details = NotificationDetails(
      android: AndroidNotificationDetails(
        _channelId,
        _channelName,
        channelDescription: '一起学习完成后的本地震动提醒',
        importance: Importance.high,
        priority: Priority.high,
        playSound: false,
        enableVibration: true,
        vibrationPattern: Int64List.fromList(<int>[0, 500, 220, 500]),
        icon: '@mipmap/ic_launcher',
      ),
    );
    final scheduled = timezone.TZDateTime.from(endAt.toUtc(), timezone.local);
    try {
      await _plugin.zonedSchedule(
        id: _notificationId,
        title: '一起学习',
        body: '这一轮学习结束了，休息一下吧。',
        scheduledDate: scheduled,
        notificationDetails: details,
        androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
        payload: 'study_focus',
      );
    } on Object {
      try {
        await _plugin.zonedSchedule(
          id: _notificationId,
          title: '一起学习',
          body: '这一轮学习结束了，休息一下吧。',
          scheduledDate: scheduled,
          notificationDetails: details,
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
          payload: 'study_focus',
        );
      } on Object {
        // The foreground timer still completes when notifications are denied.
      }
    }
  }

  Future<void> cancel() async {
    try {
      await initialize();
    } on Object {
      return;
    }
    if (!_initialized) return;
    try {
      await _plugin.cancel(id: _notificationId);
    } on Object {
      // Cancellation failure must not block pause or completion state changes.
    }
  }
}
