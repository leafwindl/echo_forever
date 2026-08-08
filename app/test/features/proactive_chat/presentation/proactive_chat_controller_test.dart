import 'package:dio/dio.dart';
import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/proactive_chat/data/proactive_chat_api.dart';
import 'package:echo_app/features/proactive_chat/data/proactive_chat_providers.dart';
import 'package:echo_app/features/proactive_chat/domain/proactive_chat.dart';
import 'package:echo_app/features/proactive_chat/presentation/proactive_chat_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';

void main() {
  test(
    'removes a deleted task locally without a second list request',
    () async {
      const task = ChatSchedule(
        scheduleId: 'task-1',
        createdBy: 'user_request',
        scheduleType: 'once',
        intent: 'drink water',
        label: '喝水',
        timezone: 'Asia/Shanghai',
        nextRunAt: null,
        status: 'active',
      );
      final api = _FakeProactiveChatApi(task);
      final container = ProviderContainer(
        overrides: [
          secureStoreProvider.overrideWithValue(
            FakeSessionStore(testSession()),
          ),
          proactiveChatApiProvider.overrideWithValue(api),
        ],
    );
    addTearDown(container.dispose);
    await container.read(sessionControllerProvider.future);
    await container.read(proactiveChatControllerProvider.future);

      await container
          .read(proactiveChatControllerProvider.notifier)
          .deleteSchedule(task);

      expect(api.deletedIds, <String>['task-1']);
      expect(api.listCalls, 1);
      expect(
        container.read(proactiveChatControllerProvider).value?.schedules,
        isEmpty,
      );
    },
  );
}

class _FakeProactiveChatApi extends ProactiveChatApi {
  _FakeProactiveChatApi(this.task) : super(DioClient(Dio()));

  final ChatSchedule task;
  final List<String> deletedIds = <String>[];
  int listCalls = 0;

  @override
  Future<ProactiveChatPreferences> getPreferences() async =>
      const ProactiveChatPreferences.defaults();

  @override
  Future<List<ChatSchedule>> listSchedules() async {
    listCalls += 1;
    return <ChatSchedule>[task];
  }

  @override
  Future<void> deleteSchedule(String scheduleId) async {
    deletedIds.add(scheduleId);
  }
}
