import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:rootlink/data/http_chat_provider.dart';
import 'package:rootlink/domain/models.dart';

void main() {
  test(
    'non-streaming completion uses the compatible message response',
    () async {
      final client = MockClient((request) async {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['stream'], isFalse);
        expect(body.containsKey('stream_options'), isFalse);
        return http.Response.bytes(
          utf8.encode(
            jsonEncode(<String, dynamic>{
              'choices': <Object>[
                <String, dynamic>{
                  'message': <String, dynamic>{'content': '完整回复'},
                },
              ],
            }),
          ),
          200,
        );
      });
      final provider = HttpChatProvider(
        const ModelConfig(
          provider: 'deepseek',
          model: 'deepseek-chat',
          apiKey: 'secret',
          baseUrl: 'https://example.test/v1',
        ),
        clientFactory: () => client,
      );
      final result = await provider.complete(
        const ChatRequest(
          model: 'deepseek-chat',
          messages: <Map<String, dynamic>>[
            <String, dynamic>{'role': 'user', 'content': '你好'},
          ],
        ),
      );
      expect(result, '完整回复');
    },
  );

  test(
    'SSE parser handles MiniMax cumulative chunks and done marker',
    () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/v1/chat/completions');
        return http.Response.bytes(
          utf8.encode(
            'data: ${jsonEncode(<String, dynamic>{
              'choices': <Object>[
                <String, dynamic>{
                  'delta': <String, dynamic>{'content': '你'},
                },
              ],
            })}\n\n'
            'data: ${jsonEncode(<String, dynamic>{
              'choices': <Object>[
                <String, dynamic>{
                  'delta': <String, dynamic>{'content': '你好'},
                },
              ],
            })}\n\n'
            'data: [DONE]\n\n',
          ),
          200,
          headers: <String, String>{'content-type': 'text/event-stream'},
        );
      });
      final provider = HttpChatProvider(
        const ModelConfig(
          provider: 'minimax',
          model: 'MiniMax-M2.5',
          apiKey: 'secret',
          baseUrl: 'https://example.test/v1',
        ),
        clientFactory: () => client,
      );
      final events = await provider
          .stream(
            const ChatRequest(
              model: 'MiniMax-M2.5',
              messages: <Map<String, dynamic>>[
                <String, dynamic>{'role': 'user', 'content': 'hi'},
              ],
            ),
          )
          .toList();
      expect(
        events
            .where((event) => event.type == ChatStreamEventType.delta)
            .map((event) => event.text)
            .join(),
        '你好',
      );
      expect(events.last.type, ChatStreamEventType.done);
    },
  );

  test('Anthropic maps tools and streams partial JSON arguments', () async {
    final client = MockClient((request) async {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      final tools = body['tools'] as List;
      expect((tools.first as Map)['input_schema'], isA<Map>());
      expect((tools.first as Map).containsKey('function'), isFalse);
      return http.Response.bytes(
        utf8.encode(
          'data: ${jsonEncode(<String, dynamic>{
            'type': 'content_block_start',
            'index': 1,
            'content_block': <String, dynamic>{'type': 'tool_use', 'id': 'tool-1', 'name': 'lookup', 'input': <String, dynamic>{}},
          })}\n\n'
          'data: ${jsonEncode(<String, dynamic>{
            'type': 'content_block_delta',
            'index': 1,
            'delta': <String, dynamic>{'type': 'input_json_delta', 'partial_json': '{"query":"hi"}'},
          })}\n\n'
          'data: ${jsonEncode(<String, dynamic>{'type': 'message_stop'})}\n\n',
        ),
        200,
        headers: <String, String>{'content-type': 'text/event-stream'},
      );
    });
    final provider = HttpChatProvider(
      const ModelConfig(
        provider: 'anthropic',
        model: 'claude-test',
        apiKey: 'secret',
        baseUrl: 'https://example.test/v1',
        apiType: 'anthropic-messages',
      ),
      clientFactory: () => client,
    );
    final events = await provider
        .stream(
          const ChatRequest(
            model: 'claude-test',
            messages: <Map<String, dynamic>>[
              <String, dynamic>{'role': 'user', 'content': '查一下'},
            ],
            tools: <Map<String, dynamic>>[
              <String, dynamic>{
                'type': 'function',
                'function': <String, dynamic>{
                  'name': 'lookup',
                  'description': 'lookup',
                  'parameters': <String, dynamic>{
                    'type': 'object',
                    'properties': <String, dynamic>{},
                  },
                },
              },
            ],
          ),
        )
        .toList();
    final calls = events
        .where((event) => event.type == ChatStreamEventType.toolCalls)
        .expand((event) => event.toolCalls)
        .toList();
    expect(calls.first['id'], 'tool-1');
    expect((calls.last['function'] as Map)['arguments'], '{"query":"hi"}');
    expect(events.last.type, ChatStreamEventType.done);
  });

  test('provider maps HTTP errors to a readable exception', () async {
    final provider = HttpChatProvider(
      const ModelConfig(
        provider: 'openai',
        model: 'test',
        apiKey: 'secret',
        baseUrl: 'https://example.test/v1',
      ),
      clientFactory: () => MockClient(
        (_) async => http.Response('{"error":{"message":"invalid key"}}', 401),
      ),
    );
    expect(
      provider
          .stream(
            const ChatRequest(
              model: 'test',
              messages: <Map<String, dynamic>>[],
            ),
          )
          .drain<void>(),
      throwsA(
        isA<ChatProviderException>().having(
          (error) => error.statusCode,
          'status',
          401,
        ),
      ),
    );
  });
}
