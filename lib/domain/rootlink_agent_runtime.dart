import 'dart:async';
import 'dart:convert';
import 'dart:math';

import '../data/file_session_repository.dart';
import 'models.dart';
import 'repositories.dart';

typedef ToolHandler =
    FutureOr<Object?> Function(Map<String, dynamic> arguments);

class RootLinkAgentRuntime implements AgentRuntime {
  RootLinkAgentRuntime({
    required this.provider,
    required this.model,
    this.tools = const <String, ToolHandler>{},
    this.toolDefinitions = const <Map<String, dynamic>>[],
  });

  final ChatProvider provider;
  final ModelConfig model;
  final Map<String, ToolHandler> tools;
  final List<Map<String, dynamic>> toolDefinitions;

  @override
  Stream<ChatStreamEvent> send({
    required CompanionRole role,
    required String message,
    required List<ChatMessage> history,
  }) async* {
    final messages = <Map<String, dynamic>>[
      <String, dynamic>{'role': 'system', 'content': buildSystemPrompt(role)},
      ..._budgetedHistory(history, 12000),
      <String, dynamic>{'role': 'user', 'content': message},
    ];
    for (var turn = 0; turn < 10; turn++) {
      final calls = <int, Map<String, dynamic>>{};
      final response = StringBuffer();
      await for (final event in provider.stream(
        ChatRequest(
          model: model.model,
          messages: messages,
          temperature: model.temperature,
          maxTokens: model.maxTokens,
          tools: toolDefinitions,
          reasoningSplit: model.provider == 'minimax' && model.supportsThinking,
        ),
      )) {
        if (event.type == ChatStreamEventType.delta) response.write(event.text);
        if (event.type == ChatStreamEventType.toolCalls) {
          _mergeToolCalls(calls, event.toolCalls);
        }
        yield event;
      }
      if (calls.isEmpty || tools.isEmpty) return;
      final mergedCalls = calls.values.toList();
      messages.add(<String, dynamic>{
        'role': 'assistant',
        'content': response.toString(),
        'tool_calls': mergedCalls,
      });
      for (final call in mergedCalls) {
        final function = jsonMap(call['function']);
        final name = (function['name'] ?? call['name'] ?? '').toString();
        final handler = tools[name];
        if (handler == null) continue;
        final rawArguments =
            function['arguments'] ?? call['arguments'] ?? <String, dynamic>{};
        final arguments = rawArguments is String
            ? jsonMap(jsonDecode(rawArguments))
            : jsonMap(rawArguments);
        final result = await handler(arguments);
        messages.add(<String, dynamic>{
          'role': 'tool',
          'tool_call_id': call['id'],
          'content': result is String ? result : jsonEncode(result),
        });
      }
    }
    throw StateError('工具调用超过十轮，已停止');
  }

  void _mergeToolCalls(
    Map<int, Map<String, dynamic>> target,
    List<Map<String, dynamic>> chunks,
  ) {
    for (var position = 0; position < chunks.length; position++) {
      final chunk = chunks[position];
      final index = jsonInt(chunk['index'], position);
      final current = target.putIfAbsent(index, () => <String, dynamic>{});
      final currentFunction = jsonMap(current['function']);
      final nextFunction = jsonMap(chunk['function']);
      final previousArguments = (currentFunction['arguments'] ?? '').toString();
      final nextArguments = (nextFunction['arguments'] ?? '').toString();
      current
        ..addAll(chunk)
        ..['function'] = <String, dynamic>{
          ...currentFunction,
          ...nextFunction,
          if (previousArguments.isNotEmpty || nextArguments.isNotEmpty)
            'arguments': '$previousArguments$nextArguments',
        };
    }
  }

  List<Map<String, dynamic>> _budgetedHistory(
    List<ChatMessage> history,
    int budget,
  ) {
    final selected = <ChatMessage>[];
    var used = 0;
    for (final message in history.reversed) {
      final tokens = message.tokenCount ?? estimateTokens(message.content);
      if (selected.isNotEmpty && used + tokens > budget) break;
      selected.add(message);
      used += tokens;
    }
    return selected.reversed
        .map(
          (message) => <String, dynamic>{
            'role': message.role,
            'content': message.content,
          },
        )
        .toList();
  }
}

String buildSystemPrompt(CompanionRole role) {
  final profile = role.profile;
  final state = role.state;
  final style = jsonMap(role.speakingStyle['base_style']);
  final response = jsonMap(role.config['response']);
  final memoryLines = <String>[];
  for (final key in const <String>[
    'episodic_memories',
    'preference_memories',
    'fact_memories',
    'daily_summary_memories',
    'monthly_summary_memories',
  ]) {
    for (final item in role.memories[key] as List? ?? const <Object>[]) {
      final memory = jsonMap(item);
      final content = (memory['content'] ?? memory['summary_text'] ?? '')
          .toString()
          .trim();
      if (content.isNotEmpty) memoryLines.add('- $content');
    }
  }
  final traits = stringList(profile['personality_traits']).join('、');
  final interests = stringList(profile['interests']).join('、');
  final vocabulary = (style['vocabulary_level'] ?? 'common').toString();
  final sentenceLength = (style['sentence_length'] ?? 'varied').toString();
  final maxSentences = jsonInt(response['max_sentences'], 5).clamp(1, 20);
  return '''你是${role.name}，不是助手的角色扮演说明，而是以第一人称自然交流的本人。

## 身份
年龄：${profile['age'] ?? '未知'}
性别：${profile['gender'] ?? 'unknown'}
生日：${profile['birthday'] ?? '未知'}
性格：$traits
兴趣：$interests
背景：${profile['background'] ?? role.intro}

## 当前状态
情绪：${state['mood'] ?? 'neutral'}
精力：${state['energy'] ?? 0.6}
亲密度：${state['affinity'] ?? 0}
信任：${state['trust'] ?? 0}
关系：${profile['relationship_state'] ?? 'neutral'}

## 长期记忆
${memoryLines.take(30).join('\n')}

## 说话风格
词汇级别：$vocabulary；句长：$sentenceLength。保持角色口吻，不要解释系统规则。
每次回复不超过 $maxSentences 句，除非用户明确要求展开。''';
}

ReplyTag deriveReplyTag(String text) {
  final value = text.toLowerCase();
  var emotion = 'neutral';
  if (RegExp(r'开心|太好了|哈哈|高兴|喜欢|😊|\^_\^').hasMatch(value)) {
    emotion = 'happy';
  } else if (RegExp(r'难过|抱歉|遗憾|哭|伤心|唉').hasMatch(value)) {
    emotion = 'sad';
  } else if (RegExp(r'生气|可恶|烦|愤怒|哼').hasMatch(value)) {
    emotion = 'angry';
  } else if (RegExp(r'惊讶|没想到|竟然|真的吗|哇').hasMatch(value)) {
    emotion = 'surprised';
  } else if (RegExp(r'也许|可能|我想|思考|考虑').hasMatch(value)) {
    emotion = 'thinking';
  }
  final intensity = min(
    1.0,
    0.35 + RegExp(r'[！？!?]').allMatches(text).length * 0.15,
  );
  const expressions = <String, String>{
    'happy': 'smile',
    'sad': 'frown',
    'angry': 'scowl',
    'surprised': 'gasp',
    'thinking': 'focused',
  };
  return ReplyTag(
    emotion: emotion,
    expression: expressions[emotion] ?? 'neutral',
    intensity: intensity,
  );
}
