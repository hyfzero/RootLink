import 'package:flutter_test/flutter_test.dart';

import 'package:rootlink/features/roles/role_memory_draft.dart';

void main() {
  Map<String, dynamic> source() => <String, dynamic>{
    'episodic_memories': <Object>[
      <String, dynamic>{
        'id': 'episode-1',
        'content': '第一次见面',
        'memory_type': 'episodic',
        'timestamp': 10,
        'importance': 1.2,
        'context': '初次对话',
        'future_entry_field': <String, dynamic>{'kept': true},
      },
    ],
    'preference_memories': <Object>[
      <String, dynamic>{
        'id': 'preference-1',
        'content': '喜欢爵士乐',
        'memory_type': 'invalid-legacy-value',
        'timestamp': 11,
      },
    ],
    'fact_memories': <Object>[
      <String, dynamic>{
        'id': 'fact-1',
        'content': '住在上海',
        'memory_type': 'fact',
        'timestamp': 12,
      },
    ],
    'daily_summary_memories': <Object>[
      <String, dynamic>{
        'id': 'daily-1',
        'summary_text': '今天聊了音乐',
        'future_summary_field': 7,
      },
    ],
    'monthly_summary_memories': <Object>[
      <String, dynamic>{'id': 'month-1', 'content': '本月关系更亲近'},
    ],
    'future_memory_array': <Object>[
      <String, dynamic>{'opaque': true},
    ],
    'future_top_level': <String, dynamic>{'kept': true},
  };

  test('reads five categories and infers invalid base memory types', () {
    final draft = RoleMemoryDraft.fromJson(source());

    expect(draft.entries, hasLength(3));
    expect(draft.entries.map((entry) => entry.memoryType), <String>[
      'episodic',
      'preference',
      'fact',
    ]);
    expect(draft.summaries('daily_summary').single['summary_text'], '今天聊了音乐');
    expect(draft.summaries('monthly_summary').single['content'], '本月关系更亲近');
  });

  test('moves, edits and deletes base memories without touching summaries', () {
    final original = source();
    final draft = RoleMemoryDraft.fromJson(original);
    final episode = draft.entries.first;
    draft.entries[0] = episode.copyWith(
      content: '第一次见面时下着雨',
      memoryType: 'preference',
      importance: 1.8,
    );
    draft.entries.removeWhere((entry) => entry.id == 'fact-1');

    final encoded = draft.toJson();
    final preferences = encoded['preference_memories'] as List;
    final moved = preferences.cast<Map>().firstWhere(
      (entry) => entry['id'] == 'episode-1',
    );

    expect(encoded['episodic_memories'], isEmpty);
    expect(encoded['fact_memories'], isEmpty);
    expect(moved['content'], '第一次见面时下着雨');
    expect(moved['memory_type'], 'preference');
    expect((moved['future_entry_field'] as Map)['kept'], isTrue);
    expect(
      encoded['daily_summary_memories'],
      original['daily_summary_memories'],
    );
    expect(
      encoded['monthly_summary_memories'],
      original['monthly_summary_memories'],
    );
    expect(encoded['future_memory_array'], original['future_memory_array']);
    expect((encoded['future_top_level'] as Map)['kept'], isTrue);
  });
}
