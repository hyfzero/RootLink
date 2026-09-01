import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import '../domain/models.dart';
import 'storage_layout.dart';

class ConversationMaintenanceService {
  ConversationMaintenanceService(this.layout);

  final StorageLayout layout;
  static const _uuid = Uuid();

  Future<void> recordReply({
    required CompanionRole role,
    required String userText,
    required String assistantText,
    required ReplyTag tag,
  }) async {
    final now = DateTime.now();
    final tagsFile = File(
      p.join(layout.brain(role.id).path, 'tags', 'reply_tags.json'),
    );
    final tags = await layout.json.readMap(tagsFile);
    final items = Map<String, dynamic>.from(jsonMap(tags['tags']));
    final order = stringList(tags['recent_order']);
    final messageId = _uuid.v4();
    items[messageId] = <String, dynamic>{
      'message_id': messageId,
      'timestamp': now.millisecondsSinceEpoch / 1000,
      'user_text': userText,
      'assistant_text': assistantText,
      ...tag.toJson(),
    };
    order.remove(messageId);
    order.add(messageId);
    final maxSize = jsonInt(tags['max_size'], 100).clamp(1, 1000);
    while (order.length > maxSize) {
      items.remove(order.removeAt(0));
    }
    await layout.json.writeMap(tagsFile, <String, dynamic>{
      ...tags,
      'tags': items,
      'recent_order': order,
      'max_size': maxSize,
    });
  }

  CompanionRole evolveRole(
    CompanionRole role, {
    required String userText,
    required String assistantText,
    required ReplyTag tag,
  }) {
    final now = DateTime.now();
    final state = Map<String, dynamic>.from(role.state);
    final ui = Map<String, dynamic>.from(role.ui);
    final interactionCount = jsonInt(state['interaction_count']) + 1;
    final positive =
        tag.emotion == 'happy' || RegExp(r'谢谢|喜欢|爱你|开心|太好').hasMatch(userText);
    final negative =
        tag.emotion == 'angry' || RegExp(r'讨厌|生气|别说了').hasMatch(userText);
    state
      ..['interaction_count'] = interactionCount
      ..['mood'] = tag.emotion
      ..['last_interaction'] = now.toIso8601String()
      ..['affinity'] =
          (jsonDouble(state['affinity'], 0.5) +
                  (positive
                      ? 0.008
                      : negative
                      ? -0.006
                      : 0.001))
              .clamp(0, 100)
      ..['trust'] = (jsonDouble(state['trust'], 0.5) + 0.001).clamp(0, 100);
    ui
      ..['last_message'] = assistantText
      ..['last_time'] = _friendlyTime(now)
      ..['last_timestamp'] = now.millisecondsSinceEpoch / 1000
      ..['emotion'] = tag.emotion;
    return role.copyWith(state: state, ui: ui);
  }

  String _friendlyTime(DateTime now) =>
      '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
}
