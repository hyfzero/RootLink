import '../../domain/models.dart';

const editableMemoryTypes = <String>['episodic', 'preference', 'fact'];

const memoryArrayByType = <String, String>{
  'episodic': 'episodic_memories',
  'preference': 'preference_memories',
  'fact': 'fact_memories',
  'daily_summary': 'daily_summary_memories',
  'monthly_summary': 'monthly_summary_memories',
};

class RoleMemoryDraft {
  RoleMemoryDraft.fromJson(Map<String, dynamic> source)
    : _source = Map<String, dynamic>.from(source),
      entries = _readEditableEntries(source);

  final Map<String, dynamic> _source;
  final List<MemoryEntry> entries;

  List<Map<String, dynamic>> summaries(String type) {
    final key = memoryArrayByType[type];
    if (key == null) return const <Map<String, dynamic>>[];
    return (_source[key] as List? ?? const <Object>[])
        .map(jsonMap)
        .toList(growable: false);
  }

  Map<String, dynamic> toJson() {
    final result = Map<String, dynamic>.from(_source);
    for (final type in editableMemoryTypes) {
      result[memoryArrayByType[type]!] = entries
          .where((entry) => entry.memoryType == type)
          .map((entry) => entry.toJson())
          .toList();
    }
    result
      ..putIfAbsent('daily_summary_memories', () => <Object>[])
      ..putIfAbsent('monthly_summary_memories', () => <Object>[]);
    return result;
  }
}

List<MemoryEntry> _readEditableEntries(Map<String, dynamic> source) {
  final entries = <MemoryEntry>[];
  for (final inferredType in editableMemoryTypes) {
    final key = memoryArrayByType[inferredType]!;
    for (final value in source[key] as List? ?? const <Object>[]) {
      final raw = jsonMap(value);
      final storedType = '${raw['memory_type'] ?? ''}';
      final normalizedType = editableMemoryTypes.contains(storedType)
          ? storedType
          : inferredType;
      entries.add(
        MemoryEntry.fromJson(<String, dynamic>{
          ...raw,
          'memory_type': normalizedType,
        }),
      );
    }
  }
  return entries;
}
