import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:rootlink/data/file_role_repository.dart';
import 'package:rootlink/data/storage_layout.dart';
import 'package:rootlink/data/zip_character_package_service.dart';
import 'package:rootlink/domain/rootlink_agent_runtime.dart';

void main() {
  test(
    'curated Kurisu package imports, builds prompt and round trips intact',
    () async {
      final first = await Directory.systemTemp.createTemp('kurisu-import-');
      final second = await Directory.systemTemp.createTemp('kurisu-roundtrip-');
      addTearDown(() async {
        await first.delete(recursive: true);
        await second.delete(recursive: true);
      });
      final layout = StorageLayout.forRoot(first);
      final service = ZipCharacterPackageService(layout);
      final id = await service.importRole('characters/kurisu_amadeus.amadues');
      expect(id, 'kurisu_amadeus');
      final role = (await FileRoleRepository(layout).getRole(id))!;
      expect(role.name, '牧濑红莉栖·Amadeus');
      expect(role.profile['relationship_state'], 'neutral');
      expect((role.memories['episodic_memories'] as List).length, 6);
      expect((role.memories['preference_memories'] as List).length, 3);
      expect((role.memories['fact_memories'] as List).length, 21);
      expect(role.memories['daily_summary_memories'], isEmpty);
      expect(role.memories['monthly_summary_memories'], isEmpty);
      final entries = role.memories.values.expand((value) => value as List).toList();
      expect(entries.map((entry) => entry['id']).toSet().length, 30);
      for (final entry in entries) {
        expect(entry['context'], contains('origin=canon_archive'));
        expect(entry['context'], contains('local_user_memory=false'));
      }
      final prompt = buildSystemPrompt(role);
      expect(prompt, contains(role.profile['background'] as String));
      expect(prompt, contains('没有与冈部共同度过本篇夏天的记忆'));
      expect(prompt, contains('非官方角色化 AI'));
      expect(prompt, contains('存在证明的自动机械'));
      expect(prompt, contains('栗悟饭和龟波气功'));
      expect(prompt, contains('2010年4月'));
      final voice = jsonDecode(
        await File(p.join(layout.brain(id).path, 'voice.json')).readAsString(),
      );
      expect(voice['voice'], 'longxiaochun_v3');
      expect(voice['is_original_character_voice'], isFalse);
      final exported = await service.exportRole(
        id,
        p.join(first.path, 'roundtrip.amadues'),
      );
      final secondLayout = StorageLayout.forRoot(second);
      await ZipCharacterPackageService(secondLayout).importRole(exported);
      final source = Directory('characters/kurisu_amadeus');
      await for (final entity in source.list(recursive: true)) {
        if (entity is! File) continue;
        final relative = p.relative(entity.path, from: source.path);
        final original = await entity.readAsBytes();
        expect(
          await File(p.join(layout.brain(id).path, relative)).readAsBytes(),
          original,
          reason: relative,
        );
        expect(
          await File(
            p.join(secondLayout.brain(id).path, relative),
          ).readAsBytes(),
          original,
          reason: 'roundtrip $relative',
        );
      }
    },
  );
}
