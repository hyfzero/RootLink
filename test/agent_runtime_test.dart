import 'package:flutter_test/flutter_test.dart';

import 'package:rootlink/domain/models.dart';
import 'package:rootlink/domain/repositories.dart';
import 'package:rootlink/domain/rootlink_agent_runtime.dart';

import 'test_fixtures.dart';

void main() {
  test(
    'runtime merges chunked tool arguments before the next model turn',
    () async {
      final provider = _ChunkedToolProvider();
      Map<String, dynamic>? received;
      final runtime = RootLinkAgentRuntime(
        provider: provider,
        model: const ModelConfig(
          provider: 'openai',
          model: 'test-model',
          apiKey: 'secret',
          baseUrl: 'https://example.test/v1',
        ),
        tools: <String, ToolHandler>{
          'lookup': (arguments) {
            received = arguments;
            return <String, dynamic>{'value': '工具结果'};
          },
        },
        toolDefinitions: const <Map<String, dynamic>>[
          <String, dynamic>{
            'type': 'function',
            'function': <String, dynamic>{'name': 'lookup'},
          },
        ],
      );

      final events = await runtime
          .send(role: fixtureRole(), message: '查询', history: const [])
          .toList();

      expect(received, <String, dynamic>{'x': 1});
      expect(provider.requests, hasLength(2));
      final secondTurn = provider.requests[1].messages;
      expect(secondTurn.any((message) => message['role'] == 'tool'), isTrue);
      expect(
        events
            .where((event) => event.type == ChatStreamEventType.delta)
            .map((event) => event.text)
            .join(),
        '完成',
      );
    },
  );
}

class _ChunkedToolProvider implements ChatProvider {
  final List<ChatRequest> requests = <ChatRequest>[];

  @override
  Future<String> complete(ChatRequest request) async => '';

  @override
  Stream<ChatStreamEvent> stream(ChatRequest request) async* {
    requests.add(request);
    if (requests.length == 1) {
      yield const ChatStreamEvent(
        type: ChatStreamEventType.toolCalls,
        toolCalls: <Map<String, dynamic>>[
          <String, dynamic>{
            'index': 0,
            'id': 'call-1',
            'function': <String, dynamic>{
              'name': 'lookup',
              'arguments': '{"x":',
            },
          },
        ],
      );
      yield const ChatStreamEvent(
        type: ChatStreamEventType.toolCalls,
        toolCalls: <Map<String, dynamic>>[
          <String, dynamic>{
            'index': 0,
            'function': <String, dynamic>{'arguments': '1}'},
          },
        ],
      );
    } else {
      yield const ChatStreamEvent(type: ChatStreamEventType.delta, text: '完成');
    }
    yield const ChatStreamEvent(type: ChatStreamEventType.done);
  }

  @override
  void cancel() {}
}
