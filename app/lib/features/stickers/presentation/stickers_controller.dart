import 'package:echo_app/core/auth_session/session_controller.dart';
import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

enum StickerSaveStep {
  idle,
  uploading,
  confirming,
  failed;

  String get label => switch (this) {
    StickerSaveStep.idle => '',
    StickerSaveStep.uploading => '正在上传图片',
    StickerSaveStep.confirming => '正在保存到私人库',
    StickerSaveStep.failed => '保存失败',
  };
}

abstract interface class StickerImagePicker {
  Future<StickerUploadSelection?> pickSticker();
}

class ImagePickerStickerImagePicker implements StickerImagePicker {
  ImagePickerStickerImagePicker({ImagePicker? picker})
    : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  @override
  Future<StickerUploadSelection?> pickSticker() async {
    final image = await _picker.pickImage(
      source: ImageSource.gallery,
      maxWidth: 1600,
      maxHeight: 1600,
      imageQuality: 92,
    );
    if (image == null) {
      return null;
    }
    return StickerUploadSelection(
      path: image.path,
      name: image.name,
      byteLength: await image.length(),
    );
  }
}

class StickersState {
  const StickersState({
    required this.items,
    required this.isLoading,
    required this.saveStep,
    this.deletingId,
    this.pendingSelection,
    this.pendingDescription = '',
    this.pendingTags = const <String>[],
    this.uploadedSticker,
    this.error,
  });

  const StickersState.loading()
    : items = const <StickerItem>[],
      isLoading = true,
      saveStep = StickerSaveStep.idle,
      deletingId = null,
      pendingSelection = null,
      pendingDescription = '',
      pendingTags = const <String>[],
      uploadedSticker = null,
      error = null;

  final List<StickerItem> items;
  final bool isLoading;
  final StickerSaveStep saveStep;
  final String? deletingId;
  final StickerUploadSelection? pendingSelection;
  final String pendingDescription;
  final List<String> pendingTags;
  final StickerItem? uploadedSticker;
  final AppException? error;

  bool get isSaving =>
      saveStep == StickerSaveStep.uploading ||
      saveStep == StickerSaveStep.confirming;

  bool get isBusy => isLoading || isSaving || deletingId != null;

  bool get canRetrySave =>
      !isBusy &&
      saveStep == StickerSaveStep.failed &&
      (pendingSelection != null || uploadedSticker != null);

  StickersState copyWith({
    List<StickerItem>? items,
    bool? isLoading,
    StickerSaveStep? saveStep,
    String? deletingId,
    bool clearDeletingId = false,
    StickerUploadSelection? pendingSelection,
    bool clearPendingSelection = false,
    String? pendingDescription,
    List<String>? pendingTags,
    bool clearPendingMetadata = false,
    StickerItem? uploadedSticker,
    bool clearUploadedSticker = false,
    AppException? error,
    bool clearError = false,
  }) {
    return StickersState(
      items: items ?? this.items,
      isLoading: isLoading ?? this.isLoading,
      saveStep: saveStep ?? this.saveStep,
      deletingId: clearDeletingId ? null : deletingId ?? this.deletingId,
      pendingSelection: clearPendingSelection
          ? null
          : pendingSelection ?? this.pendingSelection,
      pendingDescription: clearPendingMetadata
          ? ''
          : pendingDescription ?? this.pendingDescription,
      pendingTags: clearPendingMetadata
          ? const <String>[]
          : pendingTags ?? this.pendingTags,
      uploadedSticker: clearUploadedSticker
          ? null
          : uploadedSticker ?? this.uploadedSticker,
      error: clearError ? null : error ?? this.error,
    );
  }
}

class StickersController extends AsyncNotifier<StickersState> {
  static const int defaultLimit = 100;
  static const int maxUploadBytes = 5 * 1024 * 1024;
  static const List<String> _allowedExtensions = <String>[
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.webp',
  ];

  @override
  Future<StickersState> build() async {
    final session = ref.watch(sessionControllerProvider).asData?.value;
    if (session?.isAuthenticated != true) {
      return const StickersState(
        items: <StickerItem>[],
        isLoading: false,
        saveStep: StickerSaveStep.idle,
      );
    }
    try {
      return await _fetch();
    } on Object catch (error) {
      return _defaultState().copyWith(error: _asAppException(error));
    }
  }

  Future<StickersState?> refresh() async {
    final current = _currentState() ?? _defaultState();
    state = AsyncData(current.copyWith(isLoading: true, clearError: true));
    try {
      final next = await _fetch(previous: current);
      state = AsyncData(next);
      return next;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(isLoading: false, error: _asAppException(error)),
      );
      return null;
    }
  }

  Future<bool> savePickedImage(
    StickerUploadSelection selection, {
    required String description,
    required List<String> tags,
  }) async {
    final current = _currentState();
    if (current == null || current.isBusy) {
      return false;
    }
    final cleanDescription = description.trim();
    final cleanTags = tags
        .map((tag) => tag.trim())
        .where((tag) => tag.isNotEmpty)
        .toSet()
        .toList(growable: false);
    final validationError = _validate(
      selection,
      description: cleanDescription,
      tags: cleanTags,
    );
    if (validationError != null) {
      state = AsyncData(
        current.copyWith(
          saveStep: StickerSaveStep.failed,
          pendingSelection: selection,
          pendingDescription: cleanDescription,
          pendingTags: cleanTags,
          clearUploadedSticker: true,
          error: validationError,
        ),
      );
      return false;
    }
    return _completeSave(
      selection: selection,
      description: cleanDescription,
      tags: cleanTags,
    );
  }

  Future<bool> retrySavePending() async {
    final current = _currentState();
    if (current == null || !current.canRetrySave) {
      return false;
    }
    return _completeSave(
      selection: current.pendingSelection,
      uploadedSticker: current.uploadedSticker,
      description: current.pendingDescription,
      tags: current.pendingTags,
    );
  }

  Future<bool> deleteSticker(StickerItem sticker) async {
    final current = _currentState();
    if (current == null || current.isBusy || !sticker.canDelete) {
      return false;
    }
    state = AsyncData(
      current.copyWith(deletingId: sticker.stickerId, clearError: true),
    );
    try {
      await ref
          .read(stickersRepositoryProvider)
          .deleteSticker(sticker.stickerId);
      final next = await _fetch(previous: current);
      state = AsyncData(next);
      return true;
    } on Object catch (error) {
      state = AsyncData(
        current.copyWith(clearDeletingId: true, error: _asAppException(error)),
      );
      return false;
    }
  }

  void clearError() {
    final current = _currentState();
    if (current != null) {
      state = AsyncData(current.copyWith(clearError: true));
    }
  }

  Future<bool> _completeSave({
    StickerUploadSelection? selection,
    StickerItem? uploadedSticker,
    required String description,
    required List<String> tags,
  }) async {
    final current = _currentState();
    if (current == null || current.isBusy) {
      return false;
    }
    var upload = uploadedSticker;
    state = AsyncData(
      current.copyWith(
        saveStep: upload == null
            ? StickerSaveStep.uploading
            : StickerSaveStep.confirming,
        pendingSelection: selection,
        pendingDescription: description,
        pendingTags: tags,
        uploadedSticker: upload,
        clearError: true,
      ),
    );

    try {
      if (upload == null) {
        final safeSelection = selection;
        if (safeSelection == null) {
          return false;
        }
        upload = await ref
            .read(stickersRepositoryProvider)
            .uploadSticker(
              filePath: safeSelection.path,
              fileName: safeSelection.name,
              description: description,
              tags: tags,
            );
        state = AsyncData(
          (_currentState() ?? current).copyWith(
            saveStep: StickerSaveStep.confirming,
            uploadedSticker: upload,
          ),
        );
      }
      await ref.read(stickersRepositoryProvider).confirmSave(upload.stickerId);
      final next = await _fetch(previous: _currentState() ?? current);
      state = AsyncData(
        next.copyWith(
          saveStep: StickerSaveStep.idle,
          clearPendingSelection: true,
          clearPendingMetadata: true,
          clearUploadedSticker: true,
          clearError: true,
        ),
      );
      return true;
    } on Object catch (error) {
      state = AsyncData(
        (_currentState() ?? current).copyWith(
          saveStep: StickerSaveStep.failed,
          pendingSelection: selection,
          pendingDescription: description,
          pendingTags: tags,
          uploadedSticker: upload,
          error: _asAppException(error),
        ),
      );
      return false;
    }
  }

  Future<StickersState> _fetch({StickersState? previous}) async {
    final response = await ref
        .read(stickersRepositoryProvider)
        .listStickers(query: '', limit: defaultLimit);
    return (previous ?? _defaultState()).copyWith(
      items: response.items,
      isLoading: false,
      clearDeletingId: true,
      clearError: true,
    );
  }

  StickersState _defaultState() {
    return const StickersState(
      items: <StickerItem>[],
      isLoading: false,
      saveStep: StickerSaveStep.idle,
    );
  }

  StickersState? _currentState() => state.asData?.value;

  static AppException? _validate(
    StickerUploadSelection selection, {
    required String description,
    required List<String> tags,
  }) {
    final name = selection.name.isEmpty ? selection.path : selection.name;
    final lowerName = name.toLowerCase();
    final isAllowed = _allowedExtensions.any(lowerName.endsWith);
    if (!isAllowed) {
      return const AppException(
        kind: AppExceptionKind.badRequest,
        detail: '只支持 PNG、JPG、GIF 或 WebP 图片。',
      );
    }
    if (selection.byteLength > maxUploadBytes) {
      return const AppException(
        kind: AppExceptionKind.payloadTooLarge,
        detail: '图片不能超过 5 MB。',
      );
    }
    if (description.isEmpty) {
      return const AppException(
        kind: AppExceptionKind.validation,
        detail: '请填写表情包描述。',
      );
    }
    if (description.length > 300) {
      return const AppException(
        kind: AppExceptionKind.validation,
        detail: '表情包描述不能超过 300 个字。',
      );
    }
    if (tags.isEmpty) {
      return const AppException(
        kind: AppExceptionKind.validation,
        detail: '请至少填写一个语义标签。',
      );
    }
    return null;
  }

  static AppException _asAppException(Object error) {
    if (error is AppException) {
      return error;
    }
    if (error is FormatException) {
      return AppException(
        kind: AppExceptionKind.badRequest,
        detail: error.message,
      );
    }
    return const AppException(kind: AppExceptionKind.unexpected);
  }
}

final stickerImagePickerProvider = Provider<StickerImagePicker>((ref) {
  return ImagePickerStickerImagePicker();
});

final stickersControllerProvider =
    AsyncNotifierProvider<StickersController, StickersState>(
      StickersController.new,
    );
