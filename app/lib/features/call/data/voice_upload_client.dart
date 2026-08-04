import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';

class DioVoiceUploadClient implements VoiceUploadClient {
  DioVoiceUploadClient(this._client);

  static const path = '/voice/asr';
  final DioClient _client;

  @override
  Future<String> recognize(RecordingResult recording) async {
    if (recording.format != VoiceAudioFormat.pcm16le) {
      throw ArgumentError.value(
        recording.format,
        'recording.format',
        'Only PCM16LE recordings are supported',
      );
    }

    final form = FormData.fromMap(<String, Object>{
      'audio': await MultipartFile.fromFile(
        recording.path,
        filename: 'voice.pcm',
        contentType: DioMediaType('audio', 'l16'),
      ),
    });
    final response = await _client.post<Map<String, dynamic>>(path, data: form);
    return (response.data?['user_text'] as String? ?? '').trim();
  }
}
