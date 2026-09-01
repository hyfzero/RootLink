import 'dart:io';
import 'dart:math';

import 'package:intl/intl.dart';
import 'package:path/path.dart' as p;

import '../domain/models.dart';
import '../domain/repositories.dart';
import 'conversation_summary_service.dart';
import 'storage_layout.dart';

class FileSessionRepository implements SessionRepository {
  FileSessionRepository(this.layout)
    : summaries = ConversationSummaryService(layout);

  final StorageLayout layout;
  final ConversationSummaryService summaries;
  final DateFormat _date = DateFormat('yyyy-MM-dd');

  Directory _sessionRoot(String roleId) =>
      Directory(p.join(layout.brain(roleId).path, 'session'));
  File _currentFile(String roleId, String date) =>
      File(p.join(_sessionRoot(roleId).path, 'current', '$date.json'));

  @override
  Future<DaySession> loadToday(String roleId) async {
    await archiveStale(roleId);
    final today = _date.format(DateTime.now());
    final data = await layout.json.readMap(_currentFile(roleId, today));
    if (data.isEmpty) return DaySession(date: today, messages: <ChatMessage>[]);
    return DaySession.fromJson(data);
  }

  @override
  Future<DaySession> append(String roleId, ChatMessage message) async {
    final session = await loadToday(roleId);
    var messages = <ChatMessage>[...session.messages, message];
    var tokens = messages.fold<int>(
      0,
      (sum, item) => sum + (item.tokenCount ?? estimateTokens(item.content)),
    );
    if (messages.length > 500 || tokens > 50000) {
      final average = max(50, tokens ~/ max(1, messages.length));
      final keep = (50000 ~/ average).clamp(50, 100);
      if (messages.length > keep) {
        messages = messages.sublist(messages.length - keep);
      }
      tokens = messages.fold<int>(
        0,
        (sum, item) => sum + (item.tokenCount ?? estimateTokens(item.content)),
      );
    }
    final updated = DaySession(
      date: session.date,
      messages: messages,
      messageCount: session.messageCount + 1,
      totalTokensEstimate: tokens,
      summaryGenerated: session.summaryGenerated,
      tokenEstimator: session.tokenEstimator,
      tokenizerMode: session.tokenizerMode,
      modelProvider: session.modelProvider,
      modelName: session.modelName,
      extraFields: session.extraFields,
    );
    await layout.json.writeMap(
      _currentFile(roleId, session.date),
      updated.toJson(),
    );
    return updated;
  }

  @override
  Future<void> archiveStale(String roleId) async {
    final today = _date.format(DateTime.now());
    final current = Directory(p.join(_sessionRoot(roleId).path, 'current'));
    if (!await current.exists()) return;
    await for (final entity in current.list(followLinks: false)) {
      if (entity is! File || p.extension(entity.path) != '.json') continue;
      final date = p.basenameWithoutExtension(entity.path);
      if (date == today || DateTime.tryParse(date) == null) continue;
      final destination = File(
        p.join(
          _sessionRoot(roleId).path,
          'archive',
          date.substring(0, 7),
          '$date.json',
        ),
      );
      var session = DaySession.fromJson(await layout.json.readMap(entity));
      session = await summaries.summarizeArchived(roleId, session);
      await destination.parent.create(recursive: true);
      if (await destination.exists()) await destination.delete();
      await layout.json.writeMap(destination, session.toJson());
      await entity.delete();
    }
    await summaries.summarizePreviousMonths(roleId);
  }

  @override
  Future<List<DaySession>> recent(String roleId, {int days = 30}) async {
    final files = <File>[];
    final root = _sessionRoot(roleId);
    if (!await root.exists()) return <DaySession>[];
    await for (final entity in root.list(recursive: true, followLinks: false)) {
      if (entity is File && p.extension(entity.path) == '.json') {
        files.add(entity);
      }
    }
    files.sort((a, b) => b.path.compareTo(a.path));
    final sessions = <DaySession>[];
    for (final file in files.take(days)) {
      try {
        sessions.add(DaySession.fromJson(await layout.json.readMap(file)));
      } on FormatException {
        // Preserve unreadable legacy files on disk and skip only this view item.
      }
    }
    return sessions;
  }
}

int estimateTokens(String text) {
  if (text.isEmpty) return 0;
  final cjk = RegExp(r'[\u3400-\u9fff\uf900-\ufaff]').allMatches(text).length;
  final remainder = max(0, text.runes.length - cjk);
  return max(1, cjk + (remainder / 4).ceil());
}
