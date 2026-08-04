import 'package:dio/dio.dart';
import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';

class StickersApi {
  const StickersApi(this._client);

  final DioClient _client;

  static const listPath = '/stickers';
  static const uploadPath = '/stickers/upload';
  static const itemPath = '/stickers';

  Future<StickerListResponseDto> listStickers({
    String query = '',
    int limit = 50,
  }) async {
    final response = await _client.get<Map<String, dynamic>>(
      listPath,
      queryParameters: <String, dynamic>{'query': query, 'limit': limit},
    );
    return StickerListResponseDto.fromJson(response.data!);
  }

  Future<StickerItem> uploadSticker({
    required String filePath,
    required String fileName,
    String description = '',
    List<String> tags = const <String>[],
  }) async {
    final formData = FormData.fromMap(<String, Object?>{
      'file': await MultipartFile.fromFile(filePath, filename: fileName),
      if (description.trim().isNotEmpty) 'description': description.trim(),
      if (tags.isNotEmpty) 'tags': tags.join(','),
    });
    final response = await _client.post<Map<String, dynamic>>(
      uploadPath,
      data: formData,
      options: Options(
        contentType: Headers.multipartFormDataContentType,
        sendTimeout: const Duration(seconds: 60),
        receiveTimeout: const Duration(seconds: 120),
      ),
    );
    return StickerItem.fromJson(response.data!);
  }

  Future<StickerItem> confirmSave(String stickerId) async {
    final response = await _client.post<Map<String, dynamic>>(
      '$itemPath/${Uri.encodeComponent(stickerId)}/confirm-save',
    );
    return StickerItem.fromJson(response.data!);
  }

  Future<void> deleteSticker(String stickerId) async {
    await _client.delete<void>('$itemPath/${Uri.encodeComponent(stickerId)}');
  }
}

class StickerListResponseDto {
  const StickerListResponseDto({required this.items});

  factory StickerListResponseDto.fromJson(Map<String, dynamic> json) {
    return StickerListResponseDto(
      items: (json['items'] as List? ?? const <Object?>[])
          .whereType<Map<String, dynamic>>()
          .map(StickerItem.fromJson)
          .toList(growable: false),
    );
  }

  final List<StickerItem> items;
}
