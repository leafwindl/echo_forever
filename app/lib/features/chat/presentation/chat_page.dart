import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:echo_app/features/auth/presentation/auth_controller.dart';
import 'package:echo_app/features/chat/domain/chat_message.dart';
import 'package:echo_app/features/chat/presentation/chat_controller.dart';
import 'package:echo_app/shared/widgets/character_renderer.dart';
import 'package:echo_app/shared/widgets/confirm_action_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

enum _ChatMenuAction { clearContext, logout }

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
    _scheduleScrollToBottom();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Echo'),
        actions: <Widget>[
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
                    chatExpanded: state.chatExpanded,
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
                onToggleExpanded: () => ref
                    .read(chatControllerProvider.notifier)
                    .toggleChatExpanded(),
                onDismissError: () =>
                    ref.read(chatControllerProvider.notifier).clearError(),
                onOpenSource: _openSource,
                onCopySource: _copySource,
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
    if (state.isBusy || message.isEmpty || message.length > 2000) {
      return;
    }
    _inputController.clear();
    setState(() => _inputText = '');
    unawaited(ref.read(chatControllerProvider.notifier).sendMessage(message));
  }

  Future<void> _handleMenuAction(_ChatMenuAction action) async {
    switch (action) {
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
    required this.onToggleExpanded,
    required this.onDismissError,
    required this.onOpenSource,
    required this.onCopySource,
  });

  final ChatState state;
  final ScrollController scrollController;
  final TextEditingController inputController;
  final FocusNode inputFocusNode;
  final String inputText;
  final ValueChanged<String> onInputChanged;
  final VoidCallback onSend;
  final VoidCallback onToggleExpanded;
  final VoidCallback onDismissError;
  final ValueChanged<ChatSource> onOpenSource;
  final ValueChanged<ChatSource> onCopySource;

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
          if (state.isClearing) const LinearProgressIndicator(minHeight: 2),
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
              itemCount: state.messages.length,
              itemBuilder: (context, index) {
                final message = state.messages[index];
                return _MessageBubble(
                  key: ValueKey<String>('chat-message-${message.id}'),
                  message: message,
                  onOpenSource: onOpenSource,
                  onCopySource: onCopySource,
                );
              },
            ),
          ),
          _ChatInput(
            controller: inputController,
            focusNode: inputFocusNode,
            enabled: !state.isBusy,
            isSending: state.isSending,
            canSend: inputText.trim().isNotEmpty,
            onChanged: onInputChanged,
            onSend: onSend,
          ),
        ],
      ),
    );
  }
}

class _ChatInput extends StatelessWidget {
  const _ChatInput({
    required this.controller,
    required this.focusNode,
    required this.enabled,
    required this.isSending,
    required this.canSend,
    required this.onChanged,
    required this.onSend,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;
  final bool isSending;
  final bool canSend;
  final ValueChanged<String> onChanged;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: <Widget>[
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
              child: Text(isSending ? '等待' : '发送'),
            ),
          ],
        ),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.message,
    required this.onOpenSource,
    required this.onCopySource,
    super.key,
  });

  final ChatMessage message;
  final ValueChanged<ChatSource> onOpenSource;
  final ValueChanged<ChatSource> onCopySource;

  @override
  Widget build(BuildContext context) {
    final isUser = message.sender == ChatMessageSender.user;
    final colorScheme = Theme.of(context).colorScheme;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
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
                  if (message.sticker?.safeUri
                      case final Uri stickerUri) ...<Widget>[
                    const SizedBox(height: 8),
                    CachedNetworkImage(
                      imageUrl: stickerUri.toString(),
                      width: 144,
                      height: 144,
                      fit: BoxFit.contain,
                      errorWidget: (context, url, error) => const SizedBox(
                        width: 144,
                        height: 64,
                        child: Center(child: Text('表情加载失败')),
                      ),
                    ),
                  ],
                  for (final source in message.sources)
                    _SourceTile(
                      source: source,
                      onOpen: () => onOpenSource(source),
                      onCopy: () => onCopySource(source),
                    ),
                ],
              ),
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
