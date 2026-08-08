import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/proactive_chat/data/proactive_chat_api.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('lists only the server-provided active and paused tasks', () async {
    final client = _FakeDioClient(
      getResponse: <String, dynamic>{
        'items': <Map<String, dynamic>>[
          <String, dynamic>{
            'schedule_id': 'task-1',
            'created_by': 'user_request',
            'schedule_type': 'once',
            'intent': 'drink water',
            'user_visible_label': '喝水',
            'timezone': 'Asia/Shanghai',
            'next_run_at': '2026-08-08T12:00:00Z',
            'status': 'active',
          },
        ],
      },
    );

    final tasks = await ProactiveChatApi(client).listSchedules();

    expect(client.getPath, '/proactive/schedules');
    expect(tasks.single.scheduleId, 'task-1');
    expect(tasks.single.isActive, isTrue);
  });

  test('deletes a task through the DELETE endpoint', () async {
    final client = _FakeDioClient();

    await ProactiveChatApi(client).deleteSchedule('task/1');

    expect(client.deletePath, '/proactive/schedules/task%2F1');
  });
}

class _FakeDioClient extends DioClient {
  _FakeDioClient({this.getResponse}) : super(Dio());

  final Map<String, dynamic>? getResponse;
  String? getPath;
  String? deletePath;

  @override
  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    getPath = path;
    return Response<T>(
      data: getResponse as T,
      requestOptions: RequestOptions(path: path),
    );
  }

  @override
  Future<Response<T>> delete<T>(
    String path, {
    Object? data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    deletePath = path;
    return Response<T>(requestOptions: RequestOptions(path: path));
  }
}
