import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:echo_app/core/routing/route_names.dart';
import 'package:echo_app/features/app_update/presentation/app_update_controller.dart';
import 'package:echo_app/features/auth/presentation/auth_controller.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/presentation/chat_controller.dart';
import 'package:echo_app/features/letters/presentation/letters_controller.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';
import 'package:echo_app/features/stickers/presentation/stickers_controller.dart';
import 'package:echo_app/shared/widgets/character_renderer.dart';
import 'package:echo_app/shared/widgets/confirm_action_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

enum _ChatMenuAction {
  persona,
  memory,
  stickers,
  notificationSettings,
  appUpdate,
  clearContext,
  logout,
}

typedef CharacterBuilder = Widget Function(bool chatExpanded);

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({this.characterBuilder, super.key});

  final CharacterBuilder? characterBuilder;

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage> {
  final ScrollController _scrollController = ScrollController();
  final TextEditingController _inputController = TextEditingController();
  final FocusNode _inputFocusNode = FocusNode();
  String _inputText = '';
  String? _lastTailSignature;
  bool _historyLoadInFlight = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScroll);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    _inputController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(chatControllerProvider);
    final unreadLetterCount = ref.watch(lettersUnreadCountProvider);
    _scheduleScrollForState(state);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Echo'),
        actions: <Widget>[
          IconButton(
            key: const Key('open-letters-button'),
            tooltip: 'Echo 来信',
            onPressed: state.isBusy
                ? null
                : () => context.pushNamed(RouteNames.letters),
            icon: Badge(
              isLabelVisible: unreadLetterCount > 0,
              label: Text(
                unreadLetterCount > 99 ? '99+' : unreadLetterCount.toString(),
              ),
              child: const Icon(Icons.mail_outline_rounded),
            ),
          ),
          IconButton(
            key: const Key('open-call-button'),
            tooltip: '与 Echo 通话',
            onPressed: state.isBusy ? null : () => context.push('/call'),
            icon: const Icon(Icons.call_rounded),
          ),
          PopupMenuButton<_ChatMenuAction>(
            tooltip: '聊天菜单',
            enabled: !state.isBusy,
            onSelected: _handleMenuAction,
            itemBuilder: (context) => const <PopupMenuEntry<_ChatMenuAction>>[
              PopupMenuItem<_ChatMenuAction>(
                value: _ChatMenuAction.persona,
                child: Text('个性化设置'),
              ),
              PopupMenuItem<_ChatMenuAction>(
                value: _ChatMenuAction.memory,
                child: Text('长期记忆'),
              ),
              PopupMenuItem<_ChatMenuAction>(
                value: _ChatMenuAction.stickers,
                child: Text('表情包库'),
              ),
              PopupMenuItem<_ChatMenuAction>(
                value: _ChatMenuAction.notificationSettings,
                child: Text('通知设置'),
              ),
              PopupMenuItem<_ChatMenuAction>(
                value: _ChatMenuAction.appUpdate,
                child: Text('检查更新'),
              ),
              PopupMenuItem<_ChatMenuAction>(
                value: _ChatMenuAction.clearContext,
                child: Text('清除聊天上下文'),
              ),
              PopupMenuItem<_ChatMenuAction>(
                value: _ChatMenuAction.logout,
                child: Text('退出登录'),
              ),
            ],
          ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: <Widget>[
            Flexible(
              flex: state.chatExpanded ? 3 : 7,
              child:
                  widget.characterBuilder?.call(state.chatExpanded) ??
                  StaticCharacterRenderer(
                    state: state.chatExpanded
                        ? CharacterDisplayState.sitting
                        : CharacterDisplayState.idle,
                    key: const Key('static-character-renderer'),
                  ),
            ),
            Flexible(
              flex: state.chatExpanded ? 7 : 3,
              child: _ChatPanel(
                state: state,
                scrollController: _scrollController,
                inputController: _inputController,
                inputFocusNode: _inputFocusNode,
                inputText: _inputText,
                onInputChanged: (value) => setState(() => _inputText = value),
                onSend: _send,
                onOpenStickers: _openStickerPicker,
                onToggleExpanded: () => ref
                    .read(chatControllerProvider.notifier)
                    .toggleChatExpanded(),
                onDismissError: () =>
                    ref.read(chatControllerProvider.notifier).clearError(),
                onLoadOlder: _loadOlderMessages,
                onOpenSource: _openSource,
                onCopySource: _copySource,
                onRetryMessage: (clientMessageId) => unawaited(
                  ref
                      .read(chatControllerProvider.notifier)
                      .retryMessage(clientMessageId),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _send() {
    final state = ref.read(chatControllerProvider);
    final message = _inputController.text.trim();
    if (!state.canCompose || message.isEmpty || message.length > 2000) {
      return;
    }
    _inputController.clear();
    setState(() => _inputText = '');
    unawaited(ref.read(chatControllerProvider.notifier).sendMessage(message));
  }

  Future<void> _openStickerPicker() async {
    if (!ref.read(chatControllerProvider).canCompose) {
      return;
    }
    _inputFocusNode.unfocus();
    final sticker = await showModalBottomSheet<StickerItem>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => _StickerPickerSheet(
        onManage: () {
          Navigator.of(sheetContext).pop();
          unawaited(context.pushNamed(RouteNames.stickers));
        },
      ),
    );
    if (sticker == null || !mounted) {
      return;
    }
    final uri = sticker.safeUri;
    if (uri == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('该表情包暂时无法发送')));
      return;
    }
    unawaited(
      ref
          .read(chatControllerProvider.notifier)
          .sendSticker(
            ChatSticker(stickerId: sticker.stickerId, url: uri.toString()),
          ),
    );
  }

  Future<void> _handleMenuAction(_ChatMenuAction action) async {
    switch (action) {
      case _ChatMenuAction.persona:
        unawaited(context.pushNamed(RouteNames.persona));
      case _ChatMenuAction.memory:
        unawaited(context.pushNamed(RouteNames.memory));
      case _ChatMenuAction.stickers:
        unawaited(context.pushNamed(RouteNames.stickers));
      case _ChatMenuAction.notificationSettings:
        unawaited(context.pushNamed(RouteNames.notificationSettings));
      case _ChatMenuAction.appUpdate:
        await _checkForUpdate();
      case _ChatMenuAction.clearContext:
        await _confirmAndClearContext();
      case _ChatMenuAction.logout:
        final confirmed = await showConfirmActionSheet(
          context,
          title: '要退出当前账号吗？',
          actionLabel: '退出登录',
        );
        if (confirmed && mounted) {
          await ref.read(authControllerProvider.notifier).logout();
        }
    }
  }

  Future<void> _checkForUpdate() async {
    final messenger = ScaffoldMessenger.of(context);
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(const SnackBar(content: Text('正在检查更新…')));
    final result = await ref
        .read(appUpdateControllerProvider.notifier)
        .checkForUpdate(manual: true);
    if (!mounted) return;
    messenger.hideCurrentSnackBar();
    switch (result) {
      case UpdateCheckResult.upToDate:
        messenger.showSnackBar(const SnackBar(content: Text('当前已经是最新版本')));
      case UpdateCheckResult.failed:
        final updateState = ref.read(appUpdateControllerProvider);
        messenger.showSnackBar(
          SnackBar(content: Text(updateState.errorMessage ?? '检查更新失败，请稍后重试')),
        );
        ref.read(appUpdateControllerProvider.notifier).clearFailure();
      case UpdateCheckResult.skipped:
        messenger.showSnackBar(const SnackBar(content: Text('更新任务正在进行中')));
      case UpdateCheckResult.available:
        break;
    }
  }

  Future<void> _confirmAndClearContext() async {
    final confirmed =
        await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('清除聊天上下文'),
            content: const Text('会清除聊天记录和会话摘要，长期记忆仍会保留。'),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('清除'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed || !mounted) {
      return;
    }
    final cleared = await ref
        .read(chatControllerProvider.notifier)
        .clearContext();
    if (cleared && mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('聊天上下文已清除')));
    }
  }

  Future<void> _openSource(ChatSource source) async {
    final uri = source.safeUri;
    if (uri == null) {
      return;
    }
    var opened = false;
    try {
      opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    } on PlatformException {
      opened = false;
    }
    if (!opened && mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('暂时无法打开该来源')));
    }
  }

  Future<void> _copySource(ChatSource source) async {
    final uri = source.safeUri;
    if (uri == null) {
      return;
    }
    try {
      await Clipboard.setData(ClipboardData(text: uri.toString()));
    } on PlatformException {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('复制来源链接失败')));
      }
      return;
    }
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('来源链接已复制')));
    }
  }

  void _handleScroll() {
    if (!_scrollController.hasClients || _historyLoadInFlight) {
      return;
    }
    final position = _scrollController.position;
    if (position.userScrollDirection == ScrollDirection.forward &&
        position.pixels <= 80) {
      unawaited(_loadOlderMessages());
    }
  }

  Future<void> _loadOlderMessages() async {
    final state = ref.read(chatControllerProvider);
    if (_historyLoadInFlight ||
        state.isBusy ||
        !state.historyInitialized ||
        !state.hasMoreHistory ||
        !_scrollController.hasClients) {
      return;
    }
    _historyLoadInFlight = true;
    final oldMaximum = _scrollController.position.maxScrollExtent;
    final oldOffset = _scrollController.position.pixels;
    try {
      final loaded = await ref
          .read(chatControllerProvider.notifier)
          .loadOlderMessages();
      if (!loaded || !mounted) {
        return;
      }
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_scrollController.hasClients) {
          return;
        }
        final newMaximum = _scrollController.position.maxScrollExtent;
        final target = (oldOffset + newMaximum - oldMaximum).clamp(
          _scrollController.position.minScrollExtent,
          newMaximum,
        );
        _scrollController.jumpTo(target);
      });
    } finally {
      _historyLoadInFlight = false;
    }
  }

  void _scheduleScrollForState(ChatState state) {
    if (!state.historyInitialized || state.messages.isEmpty) {
      return;
    }
    final tail = state.messages.last;
    final signature = <Object?>[
      tail.id,
      tail.isTyping,
      tail.content,
      tail.sticker?.stickerId,
      tail.sources.length,
      tail.sendState,
      state.echoTyping,
    ].join(':');
    if (_lastTailSignature == signature) {
      return;
    }
    _lastTailSignature = signature;
    _scheduleScrollToBottom();
  }

  void _scheduleScrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) {
        return;
      }
      unawaited(
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        ),
      );
    });
  }
}

class _ChatPanel extends StatelessWidget {
  const _ChatPanel({
    required this.state,
    required this.scrollController,
    required this.inputController,
    required this.inputFocusNode,
    required this.inputText,
    required this.onInputChanged,
    required this.onSend,
    required this.onOpenStickers,
    required this.onToggleExpanded,
    required this.onDismissError,
    required this.onLoadOlder,
    required this.onOpenSource,
    required this.onCopySource,
    required this.onRetryMessage,
  });

  final ChatState state;
  final ScrollController scrollController;
  final TextEditingController inputController;
  final FocusNode inputFocusNode;
  final String inputText;
  final ValueChanged<String> onInputChanged;
  final VoidCallback onSend;
  final VoidCallback onOpenStickers;
  final VoidCallback onToggleExpanded;
  final VoidCallback onDismissError;
  final Future<void> Function() onLoadOlder;
  final ValueChanged<ChatSource> onOpenSource;
  final ValueChanged<ChatSource> onCopySource;
  final ValueChanged<String> onRetryMessage;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Material(
      color: colorScheme.surface,
      elevation: 8,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: <Widget>[
          InkWell(
            key: const Key('chat-expand-toggle'),
            onTap: onToggleExpanded,
            child: SizedBox(
              height: 36,
              child: Center(
                child: Text(state.chatExpanded ? '▼ 收起聊天' : '▲ 展开聊天'),
              ),
            ),
          ),
          if (state.isClearing || state.isLoadingInitialHistory)
            const LinearProgressIndicator(minHeight: 2),
          if (state.errorMessage != null)
            _ChatErrorBanner(
              message: state.errorMessage!,
              onDismiss: onDismissError,
            ),
          Expanded(
            child: ListView.builder(
              key: const Key('chat-message-list'),
              controller: scrollController,
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              itemCount:
                  state.messages.length +
                  (state.hasMoreHistory || state.isLoadingMoreHistory ? 1 : 0) +
                  (state.echoTyping ? 1 : 0),
              itemBuilder: (context, index) {
                final hasHistoryControl =
                    state.hasMoreHistory || state.isLoadingMoreHistory;
                if (hasHistoryControl && index == 0) {
                  return _HistoryLoader(
                    isLoading: state.isLoadingMoreHistory,
                    onLoad: onLoadOlder,
                  );
                }
                final messageIndex = index - (hasHistoryControl ? 1 : 0);
                if (messageIndex == state.messages.length && state.echoTyping) {
                  return const _TypingIndicatorBubble();
                }
                final message = state.messages[messageIndex];
                return _MessageBubble(
                  key: ValueKey<String>('chat-message-${message.id}'),
                  message: message,
                  onOpenSource: onOpenSource,
                  onCopySource: onCopySource,
                  onRetry: message.clientMessageId.isEmpty
                      ? null
                      : () => onRetryMessage(message.clientMessageId),
                );
              },
            ),
          ),
          _ChatInput(
            controller: inputController,
            focusNode: inputFocusNode,
            enabled: state.canCompose,
            canSend: inputText.trim().isNotEmpty,
            onChanged: onInputChanged,
            onSend: onSend,
            onOpenStickers: onOpenStickers,
          ),
        ],
      ),
    );
  }
}

class _HistoryLoader extends StatelessWidget {
  const _HistoryLoader({required this.isLoading, required this.onLoad});

  final bool isLoading;
  final Future<void> Function() onLoad;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 44,
      child: Center(
        child: isLoading
            ? const SizedBox.square(
                dimension: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : TextButton.icon(
                key: const Key('load-older-chat-messages'),
                onPressed: onLoad,
                icon: const Icon(Icons.history_rounded, size: 18),
                label: const Text('加载更早消息'),
              ),
      ),
    );
  }
}

class _ChatInput extends StatelessWidget {
  const _ChatInput({
    required this.controller,
    required this.focusNode,
    required this.enabled,
    required this.canSend,
    required this.onChanged,
    required this.onSend,
    required this.onOpenStickers,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;
  final bool canSend;
  final ValueChanged<String> onChanged;
  final VoidCallback onSend;
  final VoidCallback onOpenStickers;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: <Widget>[
            IconButton(
              key: const Key('chat-sticker-button'),
              tooltip: '表情包',
              onPressed: enabled ? onOpenStickers : null,
              icon: const Icon(Icons.emoji_emotions_outlined),
            ),
            Expanded(
              child: TextField(
                key: const Key('chat-input'),
                controller: controller,
                focusNode: focusNode,
                enabled: enabled,
                minLines: 1,
                maxLines: 4,
                maxLength: 2000,
                buildCounter:
                    (
                      context, {
                      required currentLength,
                      required isFocused,
                      required maxLength,
                    }) => null,
                textInputAction: TextInputAction.send,
                decoration: const InputDecoration(
                  hintText: '说点什么…',
                  isDense: true,
                ),
                onChanged: onChanged,
                onSubmitted: (_) => enabled ? onSend() : null,
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              key: const Key('chat-send-button'),
              onPressed: enabled && canSend ? onSend : null,
              child: const Icon(Icons.send_rounded),
            ),
          ],
        ),
      ),
    );
  }
}

class _StickerPickerSheet extends ConsumerWidget {
  const _StickerPickerSheet({required this.onManage});

  final VoidCallback onManage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncState = ref.watch(stickersControllerProvider);
    final current = asyncState.asData?.value;
    final items = current?.items ?? const <StickerItem>[];
    final isLoading = asyncState.isLoading || current?.isLoading == true;
    final error = current?.error;
    final height = MediaQuery.sizeOf(context).height * 0.58;

    return SafeArea(
      top: false,
      child: SizedBox(
        height: height.clamp(320.0, 560.0),
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 8, 8),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      '表情包',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  IconButton(
                    tooltip: '管理表情包',
                    onPressed: onManage,
                    icon: const Icon(Icons.photo_library_outlined),
                  ),
                  IconButton(
                    tooltip: '刷新',
                    onPressed: isLoading
                        ? null
                        : () => ref
                              .read(stickersControllerProvider.notifier)
                              .refresh(),
                    icon: const Icon(Icons.refresh_rounded),
                  ),
                ],
              ),
            ),
            if (isLoading) const LinearProgressIndicator(minHeight: 2),
            Expanded(
              child: switch ((items.isEmpty, isLoading, error)) {
                (true, true, _) => const Center(
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                (true, false, final error?) => _StickerPickerError(
                  message: error.detail ?? '表情包加载失败',
                  onRetry: () =>
                      ref.read(stickersControllerProvider.notifier).refresh(),
                ),
                (true, false, null) => _StickerPickerEmpty(onManage: onManage),
                _ => GridView.builder(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 20),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 4,
                    crossAxisSpacing: 8,
                    mainAxisSpacing: 8,
                  ),
                  itemCount: items.length,
                  itemBuilder: (context, index) {
                    final sticker = items[index];
                    return _StickerPickerTile(sticker: sticker);
                  },
                ),
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _StickerPickerTile extends StatelessWidget {
  const _StickerPickerTile({required this.sticker});

  final StickerItem sticker;

  @override
  Widget build(BuildContext context) {
    final uri = sticker.safeUri;
    final colorScheme = Theme.of(context).colorScheme;
    return Material(
      color: colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(8),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        key: ValueKey<String>('send-sticker-${sticker.stickerId}'),
        onTap: uri == null ? null : () => Navigator.of(context).pop(sticker),
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: uri == null
              ? const Icon(Icons.broken_image_outlined)
              : CachedNetworkImage(
                  imageUrl: uri.toString(),
                  fit: BoxFit.contain,
                  placeholder: (context, url) => const Center(
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  errorWidget: (context, url, error) =>
                      const Icon(Icons.broken_image_outlined),
                ),
        ),
      ),
    );
  }
}

class _StickerPickerEmpty extends StatelessWidget {
  const _StickerPickerEmpty({required this.onManage});

  final VoidCallback onManage;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.emoji_emotions_outlined, size: 40),
          const SizedBox(height: 10),
          const Text('还没有可发送的表情包'),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: onManage,
            icon: const Icon(Icons.add_photo_alternate_outlined),
            label: const Text('添加表情包'),
          ),
        ],
      ),
    );
  }
}

class _StickerPickerError extends StatelessWidget {
  const _StickerPickerError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('重试'),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.message,
    required this.onOpenSource,
    required this.onCopySource,
    required this.onRetry,
    super.key,
  });

  final ChatMessage message;
  final ValueChanged<ChatSource> onOpenSource;
  final ValueChanged<ChatSource> onCopySource;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final isUser = message.sender == ChatMessageSender.user;
    final colorScheme = Theme.of(context).colorScheme;
    final stickerUri = message.sticker?.safeUri;
    final hasTextBubble =
        message.isTyping ||
        message.content.isNotEmpty ||
        message.sources.isNotEmpty;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Column(
        crossAxisAlignment: isUser
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        children: <Widget>[
          if (hasTextBubble)
            Container(
              key: ValueKey<String>('chat-text-bubble-${message.id}'),
              margin: const EdgeInsets.symmetric(vertical: 4),
              constraints: BoxConstraints(
                maxWidth: MediaQuery.sizeOf(context).width * 0.78,
              ),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: isUser
                    ? colorScheme.primaryContainer
                    : message.isError
                    ? colorScheme.errorContainer
                    : colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(18),
              ),
              child: message.isTyping
                  ? const _TypingIndicator()
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        if (message.content.isNotEmpty)
                          SelectableText(message.content),
                        for (final source in message.sources)
                          _SourceTile(
                            source: source,
                            onOpen: () => onOpenSource(source),
                            onCopy: () => onCopySource(source),
                          ),
                      ],
                    ),
            ),
          if (stickerUri case final Uri uri)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: CachedNetworkImage(
                key: ValueKey<String>('chat-sticker-image-${message.id}'),
                imageUrl: uri.toString(),
                width: 144,
                height: 144,
                fit: BoxFit.contain,
                errorWidget: (context, url, error) => const SizedBox(
                  width: 144,
                  height: 64,
                  child: Center(child: Text('表情加载失败')),
                ),
              ),
            ),
          if (isUser && message.sendState != ChatSendState.sent)
            Padding(
              padding: const EdgeInsets.only(top: 2, bottom: 2),
              child: switch (message.sendState) {
                ChatSendState.sending => const SizedBox.square(
                  dimension: 14,
                  child: CircularProgressIndicator(strokeWidth: 1.5),
                ),
                ChatSendState.failed => IconButton(
                  key: ValueKey<String>(
                    'retry-chat-message-${message.clientMessageId}',
                  ),
                  tooltip: '重新发送',
                  visualDensity: VisualDensity.compact,
                  onPressed: onRetry,
                  icon: Icon(
                    Icons.error_outline_rounded,
                    size: 18,
                    color: colorScheme.error,
                  ),
                ),
                ChatSendState.sent => const SizedBox.shrink(),
              },
            ),
        ],
      ),
    );
  }
}

class _TypingIndicatorBubble extends StatelessWidget {
  const _TypingIndicatorBubble();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(18),
        ),
        child: const _TypingIndicator(),
      ),
    );
  }
}

class _TypingIndicator extends StatelessWidget {
  const _TypingIndicator();

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.onSurfaceVariant;
    return Semantics(
      key: const Key('chat-typing-indicator'),
      label: 'Echo 正在输入',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List<Widget>.generate(
          3,
          (index) => Container(
            width: 7,
            height: 7,
            margin: const EdgeInsets.symmetric(horizontal: 2),
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
        ),
      ),
    );
  }
}

class _SourceTile extends StatelessWidget {
  const _SourceTile({
    required this.source,
    required this.onOpen,
    required this.onCopy,
  });

  final ChatSource source;
  final VoidCallback onOpen;
  final VoidCallback onCopy;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 8),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: InkWell(
              onTap: onOpen,
              borderRadius: BorderRadius.circular(12),
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      '来源：${source.title}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (source.snippet.isNotEmpty)
                      Text(
                        source.snippet,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                  ],
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: '复制来源链接',
            onPressed: onCopy,
            icon: const Icon(Icons.copy_rounded, size: 18),
          ),
        ],
      ),
    );
  }
}

class _ChatErrorBanner extends StatelessWidget {
  const _ChatErrorBanner({required this.message, required this.onDismiss});

  final String message;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      color: colorScheme.errorContainer,
      padding: const EdgeInsets.only(left: 16),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: colorScheme.onErrorContainer),
            ),
          ),
          IconButton(
            tooltip: '关闭错误提示',
            onPressed: onDismiss,
            icon: const Icon(Icons.close_rounded),
          ),
        ],
      ),
    );
  }
}
