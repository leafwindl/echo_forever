import 'dart:io';

import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/stickers/data/stickers_api.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('defines stickers API paths', () {
    expect(StickersApi.listPath, '/stickers');
    expect(StickersApi.uploadPath, '/stickers/upload');
    expect(StickersApi.itemPath, '/stickers');
  });

  test('parses the backend sticker list schema', () {
    final response = StickerListResponseDto.fromJson(<String, dynamic>{
      'items': <Map<String, Object?>>[
        <String, Object?>{
          'sticker_id': 'stk-1',
          'owner_type': 'user',
          'source': 'uploaded',
          'url': 'https://cdn.example.test/stk-1.png',
          'content_type': 'image/png',
          'description': 'wave',
          'semantic_tags': <String>['hello', 'happy'],
          'status': 'active',
          'created_at': '2026-08-04T08:00:00Z',
        },
      ],
    });

    final sticker = response.items.single;
    expect(sticker.stickerId, 'stk-1');
    expect(sticker.ownerType, StickerOwnerType.user);
    expect(sticker.source, StickerSource.uploaded);
    expect(sticker.contentType, 'image/png');
    expect(sticker.semanticTags, <String>['hello', 'happy']);
    expect(sticker.canDelete, isTrue);
    expect(sticker.safeUri, Uri.parse('https://cdn.example.test/stk-1.png'));
  });

  test('defaults unknown enum values and unsafe URLs without throwing', () {
    final sticker = StickerItem.fromJson(<String, dynamic>{
      'sticker_id': 'stk-2',
      'owner_type': 'future-owner',
      'source': 'future-source',
      'url': 'javascript:alert(1)',
      'semantic_tags': <Object?>['ok', null],
    });

    expect(sticker.ownerType, StickerOwnerType.unknown);
    expect(sticker.source, StickerSource.unknown);
    expect(sticker.canDelete, isFalse);
    expect(sticker.safeUri, isNull);
  });

  test('serializes upload as multipart field named file', () async {
    final directory = await Directory.systemTemp.createTemp('echo-sticker');
    addTearDown(() async => directory.delete(recursive: true));
    final image = File('${directory.path}/wave.png');
    await image.writeAsBytes(<int>[0, 1, 2, 3]);
    final client = _CapturingDioClient();

    final uploaded = await StickersApi(client).uploadSticker(
      filePath: image.path,
      fileName: 'wave.png',
      description: 'hello',
      tags: <String>['hello', 'happy'],
    );

    final formData = client.postData as FormData;
    expect(client.postPath, StickersApi.uploadPath);
    expect(client.options?.contentType, Headers.multipartFormDataContentType);
    expect(formData.files.single.key, 'file');
    expect(formData.files.single.value.filename, 'wave.png');
    expect(Map<String, String>.fromEntries(formData.fields), <String, String>{
      'description': 'hello',
      'tags': 'hello,happy',
    });
    expect(uploaded.stickerId, 'uploaded');
  });
}

class _CapturingDioClient extends DioClient {
  _CapturingDioClient() : super(Dio());

  String? postPath;
  Object? postData;
  Options? options;

  @override
  Future<Response<T>> post<T>(
    String path, {
    Object? data,
    Options? options,
    CancelToken? cancelToken,
  }) {
    postPath = path;
    postData = data;
    this.options = options;
    return Future<Response<T>>.value(
      Response<T>(
        data:
            <String, dynamic>{
                  'sticker_id': 'uploaded',
                  'owner_type': 'user',
                  'source': 'uploaded',
                  'url': 'https://cdn.example.test/uploaded.png',
                  'content_type': 'image/png',
                  'description': 'hello',
                  'semantic_tags': <String>['hello'],
                  'status': 'processing',
                  'created_at': '2026-08-04T08:00:00Z',
                }
                as T,
        requestOptions: RequestOptions(path: path),
      ),
    );
  }
}
