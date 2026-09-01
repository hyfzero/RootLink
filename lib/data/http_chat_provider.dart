import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../domain/models.dart';
import '../domain/repositories.dart';

class ChatProviderException implements Exception {
  const ChatProviderException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

class HttpChatProvider implements ChatProvider {
  HttpChatProvider(this.config, {http.Client Function()? clientFactory})
    : _clientFactory = clientFactory ?? http.Client.new;

  final ModelConfig config;
  final http.Client Function() _clientFactory;
  http.Client? _activeClient;

  @override
  void cancel() {
    _activeClient?.close();
    _activeClient = null;
  }

  @override
  Future<String> complete(ChatRequest request) async {
    cancel();
    final client = _clientFactory();
    _activeClient = client;
    try {
      final body = _body(request)..['stream'] = false;
      body.remove('stream_options');
      final networkRequest = http.Request('POST', Uri.parse(_endpoint()))
        ..headers.addAll(_headers())
        ..body = jsonEncode(body);
      final response = await client.send(networkRequest);
      final responseBody = await response.stream.bytesToString();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ChatProviderException(
          _errorMessage(response.statusCode, responseBody),
          statusCode: response.statusCode,
        );
      }
      final data = jsonMap(jsonDecode(responseBody));
      if (config.apiType == 'anthropic-messages') {
        final content = data['content'] as List? ?? const <Object>[];
        return content
            .whereType<Map>()
            .map((item) => (item['text'] ?? '').toString())
            .where((value) => value.isNotEmpty)
            .join();
      }
      final choices = data['choices'] as List? ?? const <Object>[];
      if (choices.isEmpty) {
        return '';
      }
      final message = jsonMap(jsonMap(choices.first)['message']);
      return (message['content'] ?? message['text'] ?? '').toString();
    } on FormatException {
      throw const ChatProviderException('模型返回了无法解析的数据');
    } finally {
      if (_activeClient == client) {
        _activeClient = null;
      }
      client.close();
    }
  }

  @override
  Stream<ChatStreamEvent> stream(ChatRequest request) async* {
    cancel();
    final client = _clientFactory();
    _activeClient = client;
    try {
      final uri = Uri.parse(_endpoint());
      final networkRequest = http.Request('POST', uri)
        ..headers.addAll(_headers())
        ..body = jsonEncode(_body(request));
      final response = await client.send(networkRequest);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final body = await response.stream.bytesToString();
        throw ChatProviderException(
          _errorMessage(response.statusCode, body),
          statusCode: response.statusCode,
        );
      }
      var cumulative = '';
      await for (final line
          in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (!line.startsWith('data:')) continue;
        final payload = line.substring(5).trim();
        if (payload.isEmpty) continue;
        if (payload == '[DONE]') {
          yield const ChatStreamEvent(type: ChatStreamEventType.done);
          return;
        }
        late final Map<String, dynamic> data;
        try {
          final decoded = jsonDecode(payload);
          if (decoded is! Map) continue;
          data = decoded.cast<String, dynamic>();
        } on FormatException {
          continue;
        }
        if (config.apiType == 'anthropic-messages') {
          final events = _anthropicEvents(data);
          for (final event in events) {
            yield event;
          }
          if (events.any((event) => event.type == ChatStreamEventType.done)) {
            return;
          }
          continue;
        }
        final choices = data['choices'] as List? ?? const <Object>[];
        if (data['usage'] is Map) {
          yield ChatStreamEvent(
            type: ChatStreamEventType.usage,
            usage: (data['usage'] as Map).cast<String, dynamic>(),
          );
        }
        if (choices.isEmpty || choices.first is! Map) continue;
        final choice = (choices.first as Map).cast<String, dynamic>();
        final delta = jsonMap(choice['delta']);
        var text = (delta['content'] ?? delta['text'] ?? '').toString();
        if (config.provider == 'minimax' && text.isNotEmpty) {
          if (text.startsWith(cumulative)) {
            final next = text.substring(cumulative.length);
            cumulative = text;
            text = next;
          } else {
            cumulative += text;
          }
        } else {
          cumulative += text;
        }
        if (text.isNotEmpty) {
          yield ChatStreamEvent(type: ChatStreamEventType.delta, text: text);
        }
        final reasoning =
            (delta['reasoning_content'] ??
                    delta['reasoning'] ??
                    data['thinking'] ??
                    data['reasoning'] ??
                    '')
                .toString();
        if (reasoning.isNotEmpty) {
          yield ChatStreamEvent(
            type: ChatStreamEventType.reasoning,
            text: reasoning,
          );
        }
        final toolCalls = (delta['tool_calls'] as List? ?? const <Object>[])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList();
        if (toolCalls.isNotEmpty) {
          yield ChatStreamEvent(
            type: ChatStreamEventType.toolCalls,
            toolCalls: toolCalls,
          );
        }
        final finish = choice['finish_reason']?.toString();
        if (finish != null && finish.isNotEmpty) {
          yield ChatStreamEvent(
            type: ChatStreamEventType.done,
            finishReason: finish,
          );
          return;
        }
      }
      yield const ChatStreamEvent(type: ChatStreamEventType.done);
    } on http.ClientException catch (error) {
      if (_activeClient == client) {
        throw ChatProviderException('网络连接中断：${error.message}');
      }
    } finally {
      if (_activeClient == client) _activeClient = null;
      client.close();
    }
  }

  String _endpoint() {
    final base = config.baseUrl.replaceFirst(RegExp(r'/+$'), '');
    return config.apiType == 'anthropic-messages'
        ? '$base/messages'
        : '$base/chat/completions';
  }

  Map<String, String> _headers() {
    final headers = <String, String>{
      'content-type': 'application/json',
      'accept': 'text/event-stream',
      ...config.headers,
    };
    if (config.apiType == 'anthropic-messages') {
      headers
        ..['x-api-key'] = config.apiKey
        ..putIfAbsent('anthropic-version', () => '2023-06-01');
    } else if (config.apiKey.isNotEmpty) {
      headers['authorization'] = 'Bearer ${config.apiKey}';
    }
    if (config.provider == 'openrouter') {
      headers.putIfAbsent(
        'HTTP-Referer',
        () => 'https://github.com/amadues/rootlink',
      );
      headers.putIfAbsent('X-Title', () => 'RootLink');
    }
    return headers;
  }

  Map<String, dynamic> _body(ChatRequest request) {
    if (config.apiType == 'anthropic-messages') {
      final system = request.messages
          .where((message) => message['role'] == 'system')
          .map((message) => message['content'])
          .join('\n\n');
      final messages = _anthropicMessages(request.messages);
      final tools = request.tools.map((tool) {
        final function = jsonMap(tool['function']);
        return <String, dynamic>{
          'name': function['name'] ?? tool['name'],
          'description': function['description'] ?? tool['description'] ?? '',
          'input_schema':
              function['parameters'] ??
              tool['input_schema'] ??
              const <String, dynamic>{'type': 'object', 'properties': {}},
        };
      }).toList();
      return <String, dynamic>{
        'model': request.model,
        'system': system,
        'messages': messages,
        'temperature': request.temperature,
        'max_tokens': request.maxTokens,
        'stream': true,
        if (tools.isNotEmpty) 'tools': tools,
      };
    }
    return <String, dynamic>{
      'model': request.model,
      'messages': request.messages,
      'temperature': request.temperature,
      'max_tokens': request.maxTokens,
      'top_p': 1.0,
      'stream': true,
      'stream_options': <String, dynamic>{'include_usage': true},
      if (request.tools.isNotEmpty) 'tools': request.tools,
      if (request.reasoningSplit) 'reasoning_split': true,
    };
  }

  List<Map<String, dynamic>> _anthropicMessages(
    List<Map<String, dynamic>> source,
  ) {
    final result = <Map<String, dynamic>>[];
    for (final message in source.where(
      (message) => message['role'] != 'system',
    )) {
      final role = (message['role'] ?? 'user').toString();
      if (role == 'tool') {
        final block = <String, dynamic>{
          'type': 'tool_result',
          'tool_use_id': message['tool_call_id'],
          'content': (message['content'] ?? '').toString(),
        };
        if (result.isNotEmpty &&
            result.last['role'] == 'user' &&
            result.last['content'] is List) {
          (result.last['content'] as List).add(block);
        } else {
          result.add(<String, dynamic>{
            'role': 'user',
            'content': <Map<String, dynamic>>[block],
          });
        }
        continue;
      }
      if (role == 'assistant' && message['tool_calls'] is List) {
        final blocks = <Map<String, dynamic>>[];
        final text = (message['content'] ?? '').toString();
        if (text.isNotEmpty) {
          blocks.add(<String, dynamic>{'type': 'text', 'text': text});
        }
        for (final raw in message['tool_calls'] as List) {
          final call = jsonMap(raw);
          final function = jsonMap(call['function']);
          final rawArguments = function['arguments'] ?? call['arguments'];
          Object input = <String, dynamic>{};
          if (rawArguments is Map) {
            input = rawArguments.cast<String, dynamic>();
          } else if (rawArguments is String && rawArguments.isNotEmpty) {
            try {
              input = jsonMap(jsonDecode(rawArguments));
            } on FormatException {
              input = <String, dynamic>{};
            }
          }
          blocks.add(<String, dynamic>{
            'type': 'tool_use',
            'id': call['id'],
            'name': function['name'] ?? call['name'],
            'input': input,
          });
        }
        result.add(<String, dynamic>{'role': 'assistant', 'content': blocks});
        continue;
      }
      result.add(<String, dynamic>{
        'role': role == 'assistant' ? 'assistant' : 'user',
        'content': message['content'] ?? '',
      });
    }
    return result;
  }

  List<ChatStreamEvent> _anthropicEvents(Map<String, dynamic> data) {
    final type = data['type']?.toString();
    final delta = jsonMap(data['delta']);
    if (type == 'content_block_start') {
      final block = jsonMap(data['content_block']);
      if (block['type'] == 'tool_use') {
        final input = jsonMap(block['input']);
        return <ChatStreamEvent>[
          ChatStreamEvent(
            type: ChatStreamEventType.toolCalls,
            toolCalls: <Map<String, dynamic>>[
              <String, dynamic>{
                'index': jsonInt(data['index']),
                'id': block['id'],
                'type': 'function',
                'function': <String, dynamic>{
                  'name': block['name'],
                  'arguments': input.isEmpty ? '' : jsonEncode(input),
                },
              },
            ],
          ),
        ];
      }
    }
    if (type == 'content_block_delta') {
      final text = (delta['text'] ?? '').toString();
      final thinking = (delta['thinking'] ?? '').toString();
      final arguments = (delta['partial_json'] ?? '').toString();
      return <ChatStreamEvent>[
        if (text.isNotEmpty)
          ChatStreamEvent(type: ChatStreamEventType.delta, text: text),
        if (thinking.isNotEmpty)
          ChatStreamEvent(type: ChatStreamEventType.reasoning, text: thinking),
        if (arguments.isNotEmpty)
          ChatStreamEvent(
            type: ChatStreamEventType.toolCalls,
            toolCalls: <Map<String, dynamic>>[
              <String, dynamic>{
                'index': jsonInt(data['index']),
                'function': <String, dynamic>{'arguments': arguments},
              },
            ],
          ),
      ];
    }
    if (type == 'message_delta' && data['usage'] is Map) {
      return <ChatStreamEvent>[
        ChatStreamEvent(
          type: ChatStreamEventType.usage,
          usage: (data['usage'] as Map).cast<String, dynamic>(),
        ),
      ];
    }
    if (type == 'message_stop') {
      return const <ChatStreamEvent>[
        ChatStreamEvent(type: ChatStreamEventType.done),
      ];
    }
    return const <ChatStreamEvent>[];
  }

  String _errorMessage(int status, String body) {
    try {
      final decoded = jsonMap(jsonDecode(body));
      final error = jsonMap(decoded['error']);
      final message = error['message'] ?? decoded['message'];
      if (message != null) return '请求失败（$status）：$message';
    } on FormatException {
      // Fall through to a compact status message.
    }
    return '请求失败（HTTP $status）';
  }
}
