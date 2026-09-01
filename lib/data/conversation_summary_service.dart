import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import '../domain/models.dart';
import 'storage_layout.dart';

/// Maintains the legacy daily/monthly summary files without requiring network
/// access during startup. The next chat request can still use these summaries
/// as context, while a missing or invalid API key never blocks session archive.
class ConversationSummaryService {
  ConversationSummaryService(this.layout);

  final StorageLayout layout;
  static const _uuid = Uuid();

  Future<DaySession> summarizeArchived(
    String roleId,
    DaySession session,
  ) async {
    if (session.summaryGenerated || session.messageCount < 4) {
      return session;
    }
    final data = _dailyData(session);
    final roleRoot = layout.brain(roleId);
    await layout.json.writeMap(
      File(
        p.join(
          roleRoot.path,
          'history',
          'daily',
          '${session.date}.summary.json',
        ),
      ),
      data,
    );
    await _writeTextAtomically(
      File(
        p.join(
          roleRoot.path,
          'history',
          'summaries',
          '${session.date}.summary.md',
        ),
      ),
      _dailyMarkdown(data),
    );
    await _upsertDailyMemory(roleId, data);
    return DaySession(
      date: session.date,
      messages: session.messages,
      messageCount: session.messageCount,
      totalTokensEstimate: session.totalTokensEstimate,
      summaryGenerated: true,
      tokenEstimator: session.tokenEstimator,
      tokenizerMode: session.tokenizerMode,
      modelProvider: session.modelProvider,
      modelName: session.modelName,
      extraFields: session.extraFields,
    );
  }

  Future<void> summarizePreviousMonths(String roleId) async {
    final dailyRoot = Directory(
      p.join(layout.brain(roleId).path, 'history', 'daily'),
    );
    if (!await dailyRoot.exists()) {
      return;
    }
    final currentMonth = _month(DateTime.now());
    final byMonth = <String, List<Map<String, dynamic>>>{};
    await for (final entity in dailyRoot.list(followLinks: false)) {
      if (entity is! File || !entity.path.endsWith('.summary.json')) {
        continue;
      }
      final data = await layout.json.readMap(entity);
      final date = (data['date'] ?? '').toString();
      if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(date)) {
        continue;
      }
      final month = date.substring(0, 7);
      if (month != currentMonth) {
        byMonth.putIfAbsent(month, () => <Map<String, dynamic>>[]).add(data);
      }
    }
    for (final entry in byMonth.entries) {
      await _ensureMonthly(roleId, entry.key, entry.value);
    }
  }

  Map<String, dynamic> _dailyData(DaySession session) {
    final visible = session.messages
        .where(
          (message) => message.role == 'user' || message.role == 'assistant',
        )
        .toList();
    final excerpts = visible
        .take(6)
        .map((message) => _truncate(message.content.replaceAll('\n', ' '), 90))
        .where((value) => value.isNotEmpty)
        .toList();
    final userExcerpts = visible
        .where((message) => message.role == 'user')
        .take(3)
        .map((message) => _truncate(message.content.replaceAll('\n', ' '), 60))
        .where((value) => value.isNotEmpty)
        .toList();
    return <String, dynamic>{
      'date': session.date,
      'summary_text': excerpts.isEmpty
          ? '当日共 ${session.messageCount} 条消息。'
          : '当日围绕以下内容进行了交流：${excerpts.join('；')}',
      'important_messages': userExcerpts,
      'topics': userExcerpts,
      'emotional_tone': '中性',
      'user_preferences': <String>[],
      'unfinished_topics': <String>[],
      'message_count': session.messageCount,
      'created_at': DateTime.now().millisecondsSinceEpoch / 1000,
    };
  }

  Future<void> _ensureMonthly(
    String roleId,
    String month,
    List<Map<String, dynamic>> daily,
  ) async {
    final summaries = Directory(
      p.join(layout.brain(roleId).path, 'history', 'summaries'),
    );
    final jsonFile = File(p.join(summaries.path, '$month.monthly.json'));
    if (await jsonFile.exists()) {
      return;
    }
    daily.sort((a, b) => '${a['date']}'.compareTo('${b['date']}'));
    final topics = daily
        .expand((item) => stringList(item['topics']))
        .where((value) => value.isNotEmpty)
        .take(8)
        .toList();
    final data = <String, dynamic>{
      'year_month': month,
      'summary_text': daily
          .map((item) => '${item['date']}：${item['summary_text']}')
          .join('\n'),
      'major_events': daily
          .expand((item) => stringList(item['important_messages']))
          .take(8)
          .toList(),
      'monthly_topics': topics,
      'overall_emotional_tone': '中性',
      'user_long_term_preferences': daily
          .expand((item) => stringList(item['user_preferences']))
          .toSet()
          .take(8)
          .toList(),
      'unfinished_monthly_topics': daily
          .expand((item) => stringList(item['unfinished_topics']))
          .toSet()
          .take(8)
          .toList(),
      'growth_or_change': <String>[],
    };
    await layout.json.writeMap(jsonFile, data);
    await _writeTextAtomically(
      File(p.join(summaries.path, '$month.monthly.md')),
      '# $month 月度总结\n\n${data['summary_text']}\n',
    );
    await _replaceMonthDailyMemoriesWithMonthly(roleId, month, data);
  }

  Future<void> _upsertDailyMemory(
    String roleId,
    Map<String, dynamic> summary,
  ) async {
    final file = File(
      p.join(layout.brain(roleId).path, 'persona', 'memories.json'),
    );
    final memories = await layout.json.readMap(file);
    final daily = _mapList(memories['daily_summary_memories'])
      ..removeWhere((item) => item['context'] == '日终摘要-${summary['date']}');
    daily.add(<String, dynamic>{
      'id': 'mem_${_uuid.v4()}',
      'content': '【${summary['date']}】日终摘要: ${summary['summary_text']}',
      'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
      'memory_type': 'daily_summary',
      'importance': 0.6,
      'context': '日终摘要-${summary['date']}',
    });
    await layout.json.writeMap(file, <String, dynamic>{
      ...memories,
      'daily_summary_memories': daily,
      'updated_at': DateTime.now().millisecondsSinceEpoch / 1000,
    });
  }

  Future<void> _replaceMonthDailyMemoriesWithMonthly(
    String roleId,
    String month,
    Map<String, dynamic> summary,
  ) async {
    final file = File(
      p.join(layout.brain(roleId).path, 'persona', 'memories.json'),
    );
    final memories = await layout.json.readMap(file);
    final daily = _mapList(memories['daily_summary_memories'])
      ..removeWhere((item) => '${item['context']}'.startsWith('日终摘要-$month'));
    final monthly = _mapList(memories['monthly_summary_memories']);
    if (!monthly.any((item) => item['context'] == '月度总结-$month')) {
      monthly.add(<String, dynamic>{
        'id': 'mem_${_uuid.v4()}',
        'content': '【$month】月度总结: ${summary['summary_text']}',
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
        'memory_type': 'monthly_summary',
        'importance': 1.5,
        'context': '月度总结-$month',
      });
    }
    await layout.json.writeMap(file, <String, dynamic>{
      ...memories,
      'daily_summary_memories': daily,
      'monthly_summary_memories': monthly,
      'updated_at': DateTime.now().millisecondsSinceEpoch / 1000,
    });
  }

  List<Map<String, dynamic>> _mapList(Object? value) =>
      (value as List? ?? const <Object>[])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList();

  String _dailyMarkdown(Map<String, dynamic> data) =>
      '# ${data['date']} 对话摘要\n\n'
      '## 情感基调\n${data['emotional_tone']}\n\n'
      '## 摘要\n${data['summary_text']}\n';

  String _month(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}';

  String _truncate(String value, int length) =>
      value.length <= length ? value : '${value.substring(0, length)}…';

  Future<void> _writeTextAtomically(File target, String value) async {
    await target.parent.create(recursive: true);
    final temporary = File(
      '${target.path}.tmp.${DateTime.now().microsecondsSinceEpoch}',
    );
    await temporary.writeAsString(value, flush: true);
    if (await target.exists()) {
      await target.delete();
    }
    await temporary.rename(target.path);
  }
}
