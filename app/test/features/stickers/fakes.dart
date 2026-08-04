import 'package:echo_app/features/stickers/data/stickers_repository.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';

class FakeStickersRepository implements StickersRepository {
  FakeStickersRepository({List<StickerItem>? items})
    : items = List<StickerItem>.of(items ?? <StickerItem>[stickerFixture()]);

  List<StickerItem> items;
  Object? listError;
  Object? uploadError;
  Object? confirmError;
  Object? deleteError;
  Future<StickerItem> Function({
    required String filePath,
    required String fileName,
  })?
  onUpload;
  Future<StickerItem> Function(String stickerId)? onConfirm;
  int listCalls = 0;
  int uploadCalls = 0;
  int confirmCalls = 0;
  int deleteCalls = 0;
  final List<String> uploadedPaths = <String>[];
  final List<String> uploadedNames = <String>[];
  final List<String> confirmedIds = <String>[];
  final List<String> deletedIds = <String>[];

  @override
  Future<StickerListResult> listStickers({
    required String query,
    required int limit,
  }) async {
    listCalls += 1;
    if (listError != null) throw listError!;
    return StickerListResult(items: items.take(limit).toList(growable: false));
  }

  @override
  Future<StickerItem> uploadSticker({
    required String filePath,
    required String fileName,
    String description = '',
    List<String> tags = const <String>[],
  }) async {
    uploadCalls += 1;
    uploadedPaths.add(filePath);
    uploadedNames.add(fileName);
    if (uploadError != null) throw uploadError!;
    if (onUpload != null) {
      return onUpload!(filePath: filePath, fileName: fileName);
    }
    return stickerFixture(
      stickerId: 'uploaded-$uploadCalls',
      ownerType: StickerOwnerType.user,
      source: StickerSource.uploaded,
      status: 'processing',
      description: fileName,
    );
  }

  @override
  Future<StickerItem> confirmSave(String stickerId) async {
    confirmCalls += 1;
    confirmedIds.add(stickerId);
    if (confirmError != null) throw confirmError!;
    if (onConfirm != null) {
      return onConfirm!(stickerId);
    }
    final confirmed = stickerFixture(
      stickerId: stickerId,
      ownerType: StickerOwnerType.user,
      source: StickerSource.uploaded,
      status: 'active',
      description: 'saved sticker',
    );
    items = <StickerItem>[confirmed, ...items];
    return confirmed;
  }

  @override
  Future<void> deleteSticker(String stickerId) async {
    deleteCalls += 1;
    deletedIds.add(stickerId);
    if (deleteError != null) throw deleteError!;
    items = items
        .where((sticker) => sticker.stickerId != stickerId)
        .toList(growable: false);
  }
}

StickerItem stickerFixture({
  String stickerId = 'stk-1',
  StickerOwnerType ownerType = StickerOwnerType.user,
  StickerSource source = StickerSource.uploaded,
  String url = 'file:///sticker.png',
  String contentType = 'image/png',
  String description = 'saved sticker',
  List<String> semanticTags = const <String>['happy'],
  String status = 'active',
  String createdAt = '2026-08-04T08:00:00Z',
}) {
  return StickerItem(
    stickerId: stickerId,
    ownerType: ownerType,
    source: source,
    url: url,
    contentType: contentType,
    description: description,
    semanticTags: semanticTags,
    status: status,
    createdAt: createdAt,
  );
}
