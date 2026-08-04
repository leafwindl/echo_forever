import 'dart:io';

import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/call/data/voice_upload_client.dart';
import 'package:echo_app/features/call/domain/call_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('uploads the recorded PCM bytes without transcoding', () async {
    final directory = await Directory.systemTemp.createTemp('echo-voice');
    addTearDown(() async => directory.delete(recursive: true));
    final pcm = File('${directory.path}/recording.pcm');
    await pcm.writeAsBytes(<int>[1, 2, 3, 4]);
    final client = _CapturingDioClient();

    final text = await DioVoiceUploadClient(client).recognize(
      RecordingResult(
        path: pcm.path,
        format: VoiceAudioFormat.pcm16le,
        bytes: 4,
        duration: const Duration(milliseconds: 1),
      ),
    );

    final form = client.postData as FormData;
    final audio = form.files.single;
    expect(client.postPath, DioVoiceUploadClient.path);
    expect(audio.key, 'audio');
    expect(audio.value.filename, 'voice.pcm');
    expect(audio.value.contentType.toString(), 'audio/l16');
    expect(
      await audio.value.finalize().fold<List<int>>(<int>[], (all, part) {
        all.addAll(part);
        return all;
      }),
      <int>[1, 2, 3, 4],
    );
    expect(text, '识别结果');
  });
}

class _CapturingDioClient extends DioClient {
  _CapturingDioClient() : super(Dio());

  String? postPath;
  Object? postData;

  @override
  Future<Response<T>> post<T>(
    String path, {
    Object? data,
    Options? options,
    CancelToken? cancelToken,
  }) {
    postPath = path;
    postData = data;
    return Future<Response<T>>.value(
      Response<T>(
        data: <String, dynamic>{'user_text': ' 识别结果 '} as T,
        requestOptions: RequestOptions(path: path),
      ),
    );
  }
}
