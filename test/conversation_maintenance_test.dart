import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:rootlink/data/conversation_maintenance_service.dart';
import 'package:rootlink/data/file_session_repository.dart';
import 'package:rootlink/data/storage_layout.dart';
import 'package:rootlink/domain/models.dart';

void main() {
  late Directory temporary;
  late StorageLayout layout;

  setUp(() async {
    temporary = await Directory.systemTemp.createTemp('rootlink-maintenance-');
    layout = StorageLayout.forRoot(temporary);
  });

  tearDown(() async {
    await temporary.delete(recursive: true);
  });

  test('reply tags keep the legacy ID-indexed contract', () async {
    final role = _role('test');
    final service = ConversationMaintenanceService(layout);
    await service.recordReply(
      role: role,
      userText: '你好',
      assistantText: '很高兴见到你',
      tag: const ReplyTag(emotion: 'happy', expression: 'smile'),
    );

    final data = await layout.json.readMap(
      File(p.join(layout.brain('test').path, 'tags', 'reply_tags.json')),
    );
    final tags = jsonMap(data['tags']);
    final order = stringList(data['recent_order']);
    expect(tags, hasLength(1));
    expect(order, hasLength(1));
    expect(tags[order.single], isA<Map>());
    expect(jsonMap(tags[order.single])['message_id'], order.single);
    expect(data['max_size'], 100);
  });

  test('stale session generates compatible daily summary and memory', () async {
    final repository = FileSessionRepository(layout);
    final yesterday = DateTime.now().subtract(const Duration(days: 1));
    final date =
        '${yesterday.year.toString().padLeft(4, '0')}-'
        '${yesterday.month.toString().padLeft(2, '0')}-'
        '${yesterday.day.toString().padLeft(2, '0')}';
    final messages = List<ChatMessage>.generate(
      4,
      (index) => ChatMessage(
        id: '$index',
        role: index.isEven ? 'user' : 'assistant',
        content: '消息 $index',
        timestamp: index.toDouble(),
      ),
    );
    final current = File(
      p.join(layout.brain('test').path, 'session', 'current', '$date.json'),
    );
    await layout.json.writeMap(
      current,
      DaySession(
        date: date,
        messages: messages,
        messageCount: messages.length,
      ).toJson(),
    );
    await layout.json.writeMap(
      File(p.join(layout.brain('test').path, 'persona', 'memories.json')),
      <String, dynamic>{
        'daily_summary_memories': <Object>[],
        'monthly_summary_memories': <Object>[],
      },
    );

    await repository.archiveStale('test');

    final archived = await layout.json.readMap(
      File(
        p.join(
          layout.brain('test').path,
          'session',
          'archive',
          date.substring(0, 7),
          '$date.json',
        ),
      ),
    );
    final summary = File(
      p.join(
        layout.brain('test').path,
        'history',
        'daily',
        '$date.summary.json',
      ),
    );
    final memories = await layout.json.readMap(
      File(p.join(layout.brain('test').path, 'persona', 'memories.json')),
    );
    expect(archived['summary_generated'], isTrue);
    expect(await summary.exists(), isTrue);
    final retainedSummaries = <Object?>[
      ...(memories['daily_summary_memories'] as List? ?? const <Object>[]),
      ...(memories['monthly_summary_memories'] as List? ?? const <Object>[]),
    ];
    expect(retainedSummaries, isNotEmpty);
  });
}

CompanionRole _role(String id) => CompanionRole(
  id: id,
  profile: <String, dynamic>{'name': '测试'},
  state: <String, dynamic>{},
  memories: <String, dynamic>{},
  speakingStyle: <String, dynamic>{},
  ui: <String, dynamic>{},
  config: <String, dynamic>{},
  portraitEdits: <String, dynamic>{},
);
