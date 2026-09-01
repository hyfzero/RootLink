import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/app_state.dart';
import '../../domain/models.dart';
import '../shared/role_avatar.dart';

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key, required this.role, required this.onBack});

  final CompanionRole role;
  final VoidCallback onBack;

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  bool _immersive = false;
  int _immersiveSentence = 0;

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final chat = ref.watch(chatProvider(widget.role.id));
    final roles = ref.watch(rolesProvider).roles;
    final role =
        roles.where((item) => item.id == widget.role.id).firstOrNull ??
        widget.role;
    ref.listen(chatProvider(widget.role.id), (_, next) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.animateTo(
            _scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
          );
        }
      });
    });
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) widget.onBack();
      },
      child: Scaffold(
        appBar: AppBar(
          leading: IconButton(
            onPressed: widget.onBack,
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
          ),
          titleSpacing: 4,
          title: Row(
            children: <Widget>[
              RoleAvatar(role: role, radius: 19),
              const SizedBox(width: 11),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(role.name),
                  Text(
                    chat.isStreaming ? '正在输入…' : '本地记忆已同步',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: chat.isStreaming
                          ? Theme.of(context).colorScheme.primary
                          : Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ],
          ),
          actions: <Widget>[
            Tooltip(
              message: _immersive ? '普通聊天' : '沉浸模式',
              child: IconButton.filledTonal(
                onPressed: () => setState(() {
                  _immersive = !_immersive;
                  _immersiveSentence = 0;
                }),
                icon: Icon(
                  _immersive
                      ? Icons.chat_bubble_outline_rounded
                      : Icons.fullscreen_rounded,
                ),
              ),
            ),
            const SizedBox(width: 10),
          ],
        ),
        body: Column(
          children: <Widget>[
            Expanded(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 240),
                child: _immersive
                    ? _ImmersiveConversation(
                        key: const ValueKey('immersive'),
                        role: role,
                        state: chat,
                        sentenceIndex: _immersiveSentence,
                        onAdvance: () => setState(() => _immersiveSentence++),
                      )
                    : _BubbleConversation(
                        key: const ValueKey('bubbles'),
                        role: role,
                        state: chat,
                        controller: _scroll,
                      ),
              ),
            ),
            if (chat.error != null)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Text(
                  chat.error!,
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.onErrorContainer,
                  ),
                ),
              ),
            _Composer(
              controller: _input,
              isStreaming: chat.isStreaming,
              onSend: _send,
              onCancel: () =>
                  ref.read(chatProvider(widget.role.id).notifier).cancel(),
            ),
          ],
        ),
      ),
    );
  }

  void _send() {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    _input.clear();
    setState(() => _immersiveSentence = 0);
    ref.read(chatProvider(widget.role.id).notifier).send(text);
  }
}

class _BubbleConversation extends StatelessWidget {
  const _BubbleConversation({
    super.key,
    required this.role,
    required this.state,
    required this.controller,
  });

  final CompanionRole role;
  final ChatState state;
  final ScrollController controller;

  @override
  Widget build(BuildContext context) {
    if (state.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.messages.isEmpty) {
      return _ChatWelcome(role: role);
    }
    return ListView.builder(
      controller: controller,
      padding: const EdgeInsets.fromLTRB(18, 12, 18, 28),
      itemCount: state.messages.length + (state.reasoning.isEmpty ? 0 : 1),
      itemBuilder: (context, index) {
        if (index == state.messages.length) {
          return ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 8),
            title: const Text('模型思考过程', style: TextStyle(fontSize: 12)),
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(state.reasoning),
              ),
            ],
          );
        }
        final message = state.messages[index];
        return _MessageBubble(role: role, message: message);
      },
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.role, required this.message});
  final CompanionRole role;
  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final parts = message.isUser
        ? <String>[message.content]
        : splitSentences(message.content);
    return Align(
      alignment: message.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(
          mainAxisAlignment: message.isUser
              ? MainAxisAlignment.end
              : MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: <Widget>[
            if (!message.isUser) ...<Widget>[
              RoleAvatar(role: role, radius: 16),
              const SizedBox(width: 8),
            ],
            Flexible(
              child: Column(
                crossAxisAlignment: message.isUser
                    ? CrossAxisAlignment.end
                    : CrossAxisAlignment.start,
                children: <Widget>[
                  for (final part in parts)
                    Container(
                      margin: const EdgeInsets.only(top: 5),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 15,
                        vertical: 11,
                      ),
                      decoration: BoxDecoration(
                        color: message.isUser
                            ? Theme.of(context).colorScheme.primary
                            : Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(18).copyWith(
                          bottomRight: message.isUser
                              ? const Radius.circular(5)
                              : null,
                          bottomLeft: !message.isUser
                              ? const Radius.circular(5)
                              : null,
                        ),
                      ),
                      child: Text(
                        part.isEmpty && message.isStreaming ? '● ● ●' : part,
                        style: TextStyle(
                          height: 1.5,
                          color: message.isUser
                              ? Colors.white
                              : Theme.of(context).colorScheme.onSurface,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ImmersiveConversation extends StatelessWidget {
  const _ImmersiveConversation({
    super.key,
    required this.role,
    required this.state,
    required this.sentenceIndex,
    required this.onAdvance,
  });

  final CompanionRole role;
  final ChatState state;
  final int sentenceIndex;
  final VoidCallback onAdvance;

  @override
  Widget build(BuildContext context) {
    final last = state.messages.where((message) => !message.isUser).lastOrNull;
    final sentences = splitSentences(last?.content ?? role.intro);
    final index = sentences.isEmpty
        ? 0
        : sentenceIndex.clamp(0, sentences.length - 1);
    final text = sentences.isEmpty ? '……' : sentences[index];
    return InkWell(
      onTap: onAdvance,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: <Color>[
                  Theme.of(context).scaffoldBackgroundColor,
                  Theme.of(context).colorScheme.primary.withValues(alpha: 0.1),
                ],
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
              ),
            ),
          ),
          Positioned.fill(
            bottom: 112,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: StandingPortrait(role: role, expression: state.emotion),
            ),
          ),
          Positioned(
            left: 18,
            right: 18,
            bottom: 18,
            child: Container(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 18),
              decoration: BoxDecoration(
                color: Theme.of(
                  context,
                ).colorScheme.surface.withValues(alpha: 0.94),
                borderRadius: BorderRadius.circular(22),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    role.name,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    text,
                    style: const TextStyle(height: 1.55, fontSize: 16),
                  ),
                  const SizedBox(height: 6),
                  Align(
                    alignment: Alignment.centerRight,
                    child: Text(
                      state.isStreaming ? '生成中…' : '点击继续  ›',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChatWelcome extends StatelessWidget {
  const _ChatWelcome({required this.role});
  final CompanionRole role;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(36),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          RoleAvatar(role: role, radius: 48),
          const SizedBox(height: 18),
          Text(
            '和 ${role.name} 开始对话',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            role.intro,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    ),
  );
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.isStreaming,
    required this.onSend,
    required this.onCancel,
  });
  final TextEditingController controller;
  final bool isStreaming;
  final VoidCallback onSend;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) => SafeArea(
    top: false,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
      child: Row(
        children: <Widget>[
          IconButton(
            onPressed: () {
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(const SnackBar(content: Text('语音识别暂未启用')));
            },
            tooltip: '语音（预留）',
            icon: const Icon(Icons.mic_none_rounded),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: TextField(
              controller: controller,
              enabled: !isStreaming,
              minLines: 1,
              maxLines: 5,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
              decoration: const InputDecoration(hintText: '说点什么…'),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: isStreaming ? onCancel : onSend,
            tooltip: isStreaming ? '停止生成' : '发送',
            icon: Icon(
              isStreaming ? Icons.stop_rounded : Icons.arrow_upward_rounded,
            ),
          ),
        ],
      ),
    ),
  );
}

List<String> splitSentences(String text) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) return <String>[];
  final matches = RegExp(
    r'.+?(?:[。！？!?…]+|$)',
    dotAll: true,
  ).allMatches(trimmed);
  final result = matches
      .map((match) => match.group(0)!.trim())
      .where((part) => part.isNotEmpty)
      .toList();
  return result.isEmpty ? <String>[trimmed] : result;
}
