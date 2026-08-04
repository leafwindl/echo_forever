import 'dart:io';

import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/call/domain/call_adapters.dart';
import 'package:echo_app/features/call/domain/call_models.dart';

/// Optional deployment adapter for the approved PCM -> MP3 compatibility
/// exception described in development-plan §6.3.  It is intentionally not
/// faked by changing the MIME type.
abstract interface class PcmUploadTranscoder {
  Future<String> transcodeToMp3(String pcmPath);
}

class DioVoiceUploadClient implements VoiceUploadClient {
  DioVoiceUploadClient(this._client, [this._transcoder]);

  static const path = '/voice/asr';
  final DioClient _client;
  final PcmUploadTranscoder? _transcoder;

  @override
  Future<String> recognize(RecordingResult recording) async {
    String uploadPath = recording.path;
    var deleteConverted = false;
    if (recording.format == VoiceAudioFormat.pcm16le) {
      final transcoder = _transcoder;
      if (transcoder == null) {
        throw const VoiceFormatGateException();
      }
      uploadPath = await transcoder.transcodeToMp3(recording.path);
      deleteConverted = uploadPath != recording.path;
    }
    try {
      final form = FormData.fromMap(<String, Object>{
        'audio': await MultipartFile.fromFile(
          uploadPath,
          filename: 'voice.mp3',
          contentType: DioMediaType('audio', 'mpeg'),
        ),
      });
      final response = await _client.post<Map<String, dynamic>>(
        path,
        data: form,
      );
      return (response.data?['user_text'] as String? ?? '').trim();
    } finally {
      if (deleteConverted) {
        final file = File(uploadPath);
        if (await file.exists()) await file.delete();
      }
    }
  }
}

class VoiceFormatGateException implements Exception {
  const VoiceFormatGateException();

  @override
  String toString() =>
      'PCM fallback needs an approved PCM endpoint or a verified MP3 transcoder';
}
