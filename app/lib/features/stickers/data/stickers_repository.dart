import 'package:echo_app/features/stickers/data/stickers_api.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';

abstract interface class StickersRepository {
  Future<StickerListResult> listStickers({
    required String query,
    required int limit,
  });

  Future<StickerItem> uploadSticker({
    required String filePath,
    required String fileName,
    String description,
    List<String> tags,
  });

  Future<StickerItem> confirmSave(String stickerId);

  Future<void> deleteSticker(String stickerId);
}

class StickersRepositoryImpl implements StickersRepository {
  const StickersRepositoryImpl(this._api);

  final StickersApi _api;

  @override
  Future<StickerListResult> listStickers({
    required String query,
    required int limit,
  }) async {
    final response = await _api.listStickers(query: query, limit: limit);
    return StickerListResult(items: response.items);
  }

  @override
  Future<StickerItem> uploadSticker({
    required String filePath,
    required String fileName,
    String description = '',
    List<String> tags = const <String>[],
  }) {
    return _api.uploadSticker(
      filePath: filePath,
      fileName: fileName,
      description: description,
      tags: tags,
    );
  }

  @override
  Future<StickerItem> confirmSave(String stickerId) {
    return _api.confirmSave(stickerId);
  }

  @override
  Future<void> deleteSticker(String stickerId) {
    return _api.deleteSticker(stickerId);
  }
}
