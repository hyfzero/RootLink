import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

import 'package:rootlink/data/file_role_repository.dart';
import 'package:rootlink/data/file_settings_repository.dart';
import 'package:rootlink/data/storage_layout.dart';
import 'package:rootlink/domain/models.dart';

import 'test_fixtures.dart';

void main() {
  late Directory temp;
  late StorageLayout layout;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('rootlink-storage-test-');
    layout = StorageLayout.forRoot(temp);
    await layout.data.create(recursive: true);
    await layout.config.create(recursive: true);
  });

  tearDown(() => temp.delete(recursive: true));

  test(
    'theme defaults to light and preserves an explicit dark choice',
    () async {
      final repository = FileSettingsRepository(layout);

      expect((await repository.load()).isDark, isFalse);

      await repository.save(const UiSettings(isDark: true));
      expect((await repository.load()).isDark, isTrue);
    },
  );

  test('legacy role JSON round trip keeps unknown fields', () async {
    final repository = FileRoleRepository(layout);
    final original = fixtureRole();
    await repository.saveRole(original);

    final profileFile = File(
      p.join(layout.brain(original.id).path, 'persona', 'profile.json'),
    );
    final onDisk = jsonDecode(await profileFile.readAsString()) as Map;
    expect((onDisk['future_profile_field'] as Map)['kept'], isTrue);

    final loaded = await repository.getRole(original.id);
    expect(loaded, isNotNull);
    await repository.saveRole(
      loaded!.copyWith(
        profile: <String, dynamic>{...loaded.profile, 'name': '新名字'},
      ),
    );
    final rewritten = jsonDecode(await profileFile.readAsString()) as Map;
    expect((rewritten['future_profile_field'] as Map)['kept'], isTrue);
    expect(rewritten['name'], '新名字');
  });

  test('typed legacy values preserve fields introduced by other builds', () {
    final state = PersonalityState.fromJson(<String, dynamic>{
      'mood': 'warm',
      'affinity': 23,
      'future_state': <String, dynamic>{'kept': true},
    });
    final style = SpeakingStyle.fromJson(<String, dynamic>{
      'vocabulary_level': 'simple',
      'future_style': 7,
    });
    final portrait = PortraitEdit.fromJson(<String, dynamic>{
      'crop_box': <int>[1, 2, 30, 40],
      'future_portrait': 'kept',
    });
    final memory = MemoryEntry.fromJson(<String, dynamic>{
      'id': 'memory-1',
      'content': '记住紫色',
      'memory_type': 'preference',
      'timestamp': 123,
      'future_memory': <String, dynamic>{'kept': true},
    });
    expect((state.toJson()['future_state'] as Map)['kept'], isTrue);
    expect(style.toJson()['future_style'], 7);
    expect(portrait.toJson()['future_portrait'], 'kept');
    expect(portrait.cropBox, <int>[1, 2, 30, 40]);
    expect((memory.toJson()['future_memory'] as Map)['kept'], isTrue);
    final updatedMemory = memory.copyWith(
      content: '记住低饱和蓝色',
      memoryType: 'fact',
    );
    expect(updatedMemory.id, 'memory-1');
    expect(updatedMemory.timestamp, 123);
    expect((updatedMemory.toJson()['future_memory'] as Map)['kept'], isTrue);
  });

  test('atomic writes leave a readable backup', () async {
    final target = File(p.join(temp.path, 'config', 'value.json'));
    await layout.json.writeMap(target, <String, dynamic>{'value': 1});
    await layout.json.writeMap(target, <String, dynamic>{'value': 2});
    expect(jsonDecode(await target.readAsString()), <String, dynamic>{
      'value': 2,
    });
    final backup = File('${target.path}.bak');
    expect(backup.existsSync(), isTrue);
    expect(jsonDecode(await backup.readAsString()), <String, dynamic>{
      'value': 1,
    });
  });

  test('invalid legacy migration never replaces valid local data', () async {
    final legacy = await Directory.systemTemp.createTemp('rootlink-legacy-');
    addTearDown(() => legacy.delete(recursive: true));
    final current = File(
      p.join(temp.path, 'data', 'luna', 'persona', 'profile.json'),
    );
    await layout.json.writeMap(current, <String, dynamic>{'name': '当前角色'});
    final broken = File(
      p.join(legacy.path, 'data', 'broken', 'persona', 'profile.json'),
    );
    await broken.parent.create(recursive: true);
    await broken.writeAsString('{invalid json');

    final migrated = await layout.migrateFromLegacyDirectory(legacy);

    expect(migrated, isFalse);
    expect(layout.migrationWarning, isNotNull);
    expect(await layout.json.readMap(current), <String, dynamic>{
      'name': '当前角色',
    });
    expect(await layout.brain('broken').exists(), isFalse);
    expect(await legacy.exists(), isTrue);
  });
}
