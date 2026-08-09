import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:echo_app/features/letters/domain/letter.dart';
import 'package:echo_app/features/letters/presentation/letters_controller.dart';
import 'package:echo_app/shared/widgets/echo_loading_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class LettersPage extends ConsumerWidget {
  const LettersPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncState = ref.watch(lettersControllerProvider);
    final state = asyncState.asData?.value;
    if (state == null && asyncState.isLoading) {
      return const Scaffold(
        body: SafeArea(child: EchoLoadingView(label: '正在取回来信')),
      );
    }

    final current = state ?? const LettersState.loading();
    return Scaffold(
      appBar: AppBar(
        title: Text('Echo 来信 (${current.unreadCount})'),
        actions: <Widget>[
          IconButton(
            tooltip: '刷新',
            onPressed: current.isLoading
                ? null
                : () => ref.read(lettersControllerProvider.notifier).refresh(),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            if (current.isLoading) const LinearProgressIndicator(minHeight: 2),
            if (current.error != null)
              _LettersErrorBanner(
                message: current.error!.detail ?? '暂时没能取回来信，请稍后重试。',
                onRetry: () =>
                    ref.read(lettersControllerProvider.notifier).refresh(),
                onDismiss: () =>
                    ref.read(lettersControllerProvider.notifier).clearError(),
              ),
            Expanded(
              child:
                  current.isLoading &&
                      current.letters.isEmpty &&
                      current.error == null
                  ? const EchoLoadingView(label: '正在取回来信')
                  : RefreshIndicator(
                      onRefresh: () async {
                        await ref
                            .read(lettersControllerProvider.notifier)
                            .refresh();
                      },
                      child: current.letters.isEmpty
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
                          : ListView.separated(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(
                                16,
                                16,
                                16,
                                24,
                              ),
                              itemCount: current.letters.length,
                              separatorBuilder: (context, index) =>
                                  const SizedBox(height: 12),
                              itemBuilder: (context, index) {
                                final letter = current.letters[index];
                                return _LetterTile(
                                  key: ValueKey<String>(
                                    'letter-${letter.letterId}',
                                  ),
                                  letter: letter,
                                  opening:
                                      current.openingId == letter.letterId ||
                                      current.readingId == letter.letterId,
                                  onOpen: () =>
                                      _openLetter(context, ref, letter),
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

  void _openLetter(BuildContext context, WidgetRef ref, DailyLetter letter) {
    final controller = ref.read(lettersControllerProvider.notifier);
    unawaited(controller.openLetter(letter.letterId));
    unawaited(
      showDialog<void>(
        context: context,
        builder: (context) => _LetterDialog(initial: letter),
      ).then((_) => controller.closeLetter()),
    );
  }
}

class _LetterTile extends StatelessWidget {
  const _LetterTile({
    required this.letter,
    required this.opening,
    required this.onOpen,
    super.key,
  });

  final DailyLetter letter;
  final bool opening;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final unread = letter.status.isUnread;
    return Material(
      color: unread
          ? colorScheme.primaryContainer.withValues(alpha: 0.35)
          : colorScheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(
          color: unread ? colorScheme.primary : colorScheme.outlineVariant,
          width: unread ? 1.4 : 1,
        ),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      letter.localDate,
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  if (opening)
                    const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  else if (unread)
                    const Badge(label: Text('未读')),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                letter.subject,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              if (letter.imageUrl.isNotEmpty) ...<Widget>[
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: CachedNetworkImage(
                    imageUrl: letter.imageUrl,
                    width: double.infinity,
                    height: 120,
                    fit: BoxFit.cover,
                    placeholder: (context, url) => const SizedBox(
                      height: 120,
                      child: Center(child: CircularProgressIndicator()),
                    ),
                    errorWidget: (context, url, error) => const SizedBox.shrink(),
                  ),
                ),
                const SizedBox(height: 8),
              ],
              Text(
                letter.content,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LetterDialog extends ConsumerWidget {
  const _LetterDialog({required this.initial});

  final DailyLetter initial;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lettersControllerProvider).asData?.value;
    final letter = state?.selected ?? initial;
    final isReading = state?.readingId == letter.letterId;
    final readFailed =
        state?.error != null && letter.status.isUnread && !isReading;
    return AlertDialog(
      title: Text(letter.subject),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                '${letter.localDate} · ${letter.status.label}',
                style: Theme.of(context).textTheme.labelMedium,
              ),
              if (isReading) ...<Widget>[
                const SizedBox(height: 12),
                const LinearProgressIndicator(minHeight: 2),
              ],
              if (readFailed) ...<Widget>[
                const SizedBox(height: 12),
                Text(
                  state!.error!.detail ?? '标记已读失败，可稍后重试。',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              if (letter.imageUrl.isNotEmpty) ...<Widget>[
                const SizedBox(height: 4),
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: CachedNetworkImage(
                    imageUrl: letter.imageUrl,
                    width: double.infinity,
                    fit: BoxFit.contain,
                    placeholder: (context, url) => const SizedBox(
                      height: 180,
                      child: Center(child: CircularProgressIndicator()),
                    ),
                    errorWidget: (context, url, error) => const SizedBox.shrink(),
                  ),
                ),
              ],
              const SizedBox(height: 18),
              SelectableText(letter.content),
            ],
          ),
        ),
      ),
      actions: <Widget>[
        if (readFailed)
          TextButton(
            onPressed: () =>
                ref.read(lettersControllerProvider.notifier).markSelectedRead(),
            child: const Text('重试已读'),
          ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('收好这封信'),
        ),
      ],
    );
  }
}

class _LettersErrorBanner extends StatelessWidget {
  const _LettersErrorBanner({
    required this.message,
    required this.onRetry,
    required this.onDismiss,
  });

  final String message;
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

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        const Icon(Icons.mail_outline_rounded, size: 44),
        const SizedBox(height: 12),
        Text('今天还没有新信', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 6),
        Text(
          '我们聊过的事，会在这里慢慢沉淀下来。',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ],
    );
  }
}
