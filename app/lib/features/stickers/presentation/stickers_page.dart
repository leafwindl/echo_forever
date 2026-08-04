import 'package:cached_network_image/cached_network_image.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';
import 'package:echo_app/features/stickers/presentation/stickers_controller.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class StickersPage extends ConsumerWidget {
  const StickersPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncState = ref.watch(stickersControllerProvider);
    final state = asyncState.asData?.value;
    if (state == null && asyncState.isLoading) {
      return const Scaffold(
        body: SafeArea(child: EchoLoadingView(label: '正在加载表情包')),
      );
    }

    final current = state ?? const StickersState.loading();
    return Scaffold(
      appBar: AppBar(
        title: Text('表情包库 (${current.items.length})'),
        actions: <Widget>[
          if (current.canRetrySave)
            IconButton(
              key: const Key('retry-sticker-save-button'),
              tooltip: '重试保存',
              onPressed: () => _retrySave(context, ref),
              icon: const Icon(Icons.refresh_rounded),
            ),
          IconButton(
            key: const Key('choose-sticker-button'),
            tooltip: '添加表情',
            onPressed: current.isBusy
                ? null
                : () => _chooseSticker(context, ref),
            icon: const Icon(Icons.add_photo_alternate_rounded),
          ),
          IconButton(
            tooltip: '刷新',
            onPressed: current.isLoading
                ? null
                : () => ref.read(stickersControllerProvider.notifier).refresh(),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            if (current.isLoading || current.isSaving)
              const LinearProgressIndicator(minHeight: 2),
            if (current.isSaving)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                child: Row(
                  children: <Widget>[
                    const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    const SizedBox(width: 10),
                    Text(
                      current.saveStep.label,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
            if (current.error != null)
              _StickerErrorBanner(
                message: current.error!.detail ?? '表情包操作失败，请重试。',
                canRetry: current.canRetrySave,
                onRetry: () => _retrySave(context, ref),
                onDismiss: () =>
                    ref.read(stickersControllerProvider.notifier).clearError(),
              ),
            Expanded(
              child:
                  current.isLoading &&
                      current.items.isEmpty &&
                      current.error == null
                  ? const EchoLoadingView(label: '正在加载表情包')
                  : RefreshIndicator(
                      onRefresh: () async {
                        await ref
                            .read(stickersControllerProvider.notifier)
                            .refresh();
                      },
                      child: current.items.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: <Widget>[
                                SizedBox(
                                  height:
                                      MediaQuery.sizeOf(context).height * 0.45,
                                  child: const Center(child: _EmptyState()),
                                ),
                              ],
                            )
                          : GridView.builder(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(
                                16,
                                16,
                                16,
                                24,
                              ),
                              gridDelegate:
                                  const SliverGridDelegateWithFixedCrossAxisCount(
                                    crossAxisCount: 2,
                                    crossAxisSpacing: 12,
                                    mainAxisSpacing: 12,
                                    childAspectRatio: 0.82,
                                  ),
                              itemCount: current.items.length,
                              itemBuilder: (context, index) {
                                final sticker = current.items[index];
                                return _StickerTile(
                                  key: ValueKey<String>(
                                    'sticker-${sticker.stickerId}',
                                  ),
                                  sticker: sticker,
                                  deleting:
                                      current.deletingId == sticker.stickerId,
                                  onDelete: () =>
                                      _deleteSticker(context, ref, sticker),
                                );
                              },
                            ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _chooseSticker(BuildContext context, WidgetRef ref) async {
    StickerUploadSelection? selection;
    try {
      selection = await ref.read(stickerImagePickerProvider).pickSticker();
    } on Object {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('暂时无法打开相册')));
      }
      return;
    }
    if (selection == null) {
      return;
    }
    final saved = await ref
        .read(stickersControllerProvider.notifier)
        .savePickedImage(selection);
    if (!context.mounted) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(saved ? '已存进私人库' : '保存失败，请检查提示后重试')));
  }

  Future<void> _retrySave(BuildContext context, WidgetRef ref) async {
    final saved = await ref
        .read(stickersControllerProvider.notifier)
        .retrySavePending();
    if (!context.mounted) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(saved ? '已存进私人库' : '保存失败，请稍后重试')));
  }

  Future<void> _deleteSticker(
    BuildContext context,
    WidgetRef ref,
    StickerItem sticker,
  ) async {
    final confirmed =
        await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('删除表情包'),
            content: const Text('只会从你的私人库删除。'),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('删除'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed || !context.mounted) {
      return;
    }
    final deleted = await ref
        .read(stickersControllerProvider.notifier)
        .deleteSticker(sticker);
    if (deleted && context.mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('表情包已删除')));
    }
  }
}

class _StickerTile extends StatelessWidget {
  const _StickerTile({
    required this.sticker,
    required this.deleting,
    required this.onDelete,
    super.key,
  });

  final StickerItem sticker;
  final bool deleting;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final imageUrl = sticker.safeUri?.toString();
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colorScheme.surface,
        border: Border.all(color: colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: ColoredBox(
                  color: colorScheme.surfaceContainerHighest,
                  child: imageUrl == null
                      ? const _ImageError()
                      : CachedNetworkImage(
                          imageUrl: imageUrl,
                          fit: BoxFit.contain,
                          placeholder: (context, url) => const Center(
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          errorWidget: (context, url, error) =>
                              const _ImageError(),
                        ),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              sticker.description.isEmpty ? '未命名表情' : sticker.description,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 4),
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    '${sticker.ownerType.label} · ${sticker.source.label}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
                if (sticker.canDelete)
                  IconButton(
                    tooltip: '删除',
                    visualDensity: VisualDensity.compact,
                    onPressed: deleting ? null : onDelete,
                    icon: deleting
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.delete_outline_rounded),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _StickerErrorBanner extends StatelessWidget {
  const _StickerErrorBanner({
    required this.message,
    required this.canRetry,
    required this.onRetry,
    required this.onDismiss,
  });

  final String message;
  final bool canRetry;
  final VoidCallback onRetry;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Material(
      color: colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.only(left: 16),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Text(
                message,
                style: TextStyle(color: colorScheme.onErrorContainer),
              ),
            ),
            if (canRetry)
              TextButton(onPressed: onRetry, child: const Text('重试')),
            IconButton(
              tooltip: '关闭错误提示',
              onPressed: onDismiss,
              icon: const Icon(Icons.close_rounded),
            ),
          ],
        ),
      ),
    );
  }
}

class _ImageError extends StatelessWidget {
  const _ImageError();

  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('图片加载失败'));
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        const Icon(Icons.photo_library_outlined, size: 44),
        const SizedBox(height: 12),
        Text('还没有表情包', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 6),
        Text('先存一张喜欢的图片吧。', style: Theme.of(context).textTheme.bodyMedium),
      ],
    );
  }
}
