import 'dart:io';

import 'package:path/path.dart' as p;

import '../domain/models.dart';
import '../domain/repositories.dart';
import 'storage_layout.dart';

class FileRoleRepository implements RoleRepository {
  FileRoleRepository(this.layout);

  final StorageLayout layout;

  @override
  Future<void> seedDefaultsIfEmpty() => layout.seedBundledRoleIfEmpty();

  @override
  Future<List<CompanionRole>> listRoles() async {
    await seedDefaultsIfEmpty();
    final roles = <CompanionRole>[];
    await for (final entity in layout.data.list(followLinks: false)) {
      if (entity is! Directory || p.basename(entity.path).startsWith('.')) {
        continue;
      }
      final role = await getRole(p.basename(entity.path));
      if (role != null) roles.add(role);
    }
    roles.sort((a, b) {
      final recent = b.lastTimestamp.compareTo(a.lastTimestamp);
      return recent == 0 ? a.name.compareTo(b.name) : recent;
    });
    return roles;
  }

  @override
  Future<CompanionRole?> getRole(String id) async {
    if (!_validId(id)) return null;
    final root = layout.brain(id);
    final profileFile = File(p.join(root.path, 'persona', 'profile.json'));
    if (!await root.exists() || !await profileFile.exists()) return null;
    return CompanionRole(
      id: id,
      profile: await layout.json.readMap(profileFile),
      state: await layout.json.readMap(
        File(p.join(root.path, 'persona', 'state.json')),
      ),
      memories: await layout.json.readMap(
        File(p.join(root.path, 'persona', 'memories.json')),
        fallback: const <String, dynamic>{
          'episodic_memories': <Object>[],
          'preference_memories': <Object>[],
          'fact_memories': <Object>[],
          'daily_summary_memories': <Object>[],
          'monthly_summary_memories': <Object>[],
        },
      ),
      speakingStyle: await layout.json.readMap(
        File(p.join(root.path, 'persona', 'speaking_style.json')),
      ),
      ui: await layout.json.readMap(File(p.join(root.path, 'ui.json'))),
      config: await layout.json.readMap(File(p.join(root.path, 'config.json'))),
      portraitEdits: await layout.json.readMap(
        File(p.join(root.path, 'portrait_edits.json')),
      ),
    );
  }

  @override
  Future<void> saveRole(CompanionRole role) async {
    if (!_validId(role.id)) {
      throw const FormatException('角色 ID 只能包含字母、数字、下划线和短横线');
    }
    final root = layout.brain(role.id);
    await Future.wait(<Future<void>>[
      layout.json.writeMap(
        File(p.join(root.path, 'persona', 'profile.json')),
        role.profile,
      ),
      layout.json.writeMap(
        File(p.join(root.path, 'persona', 'state.json')),
        role.state,
      ),
      layout.json.writeMap(
        File(p.join(root.path, 'persona', 'memories.json')),
        role.memories,
      ),
      layout.json.writeMap(
        File(p.join(root.path, 'persona', 'speaking_style.json')),
        role.speakingStyle,
      ),
      layout.json.writeMap(File(p.join(root.path, 'ui.json')), role.ui),
      layout.json.writeMap(File(p.join(root.path, 'config.json')), role.config),
      if (role.portraitEdits.isNotEmpty)
        layout.json.writeMap(
          File(p.join(root.path, 'portrait_edits.json')),
          role.portraitEdits,
        ),
    ]);
  }

  @override
  Future<void> deleteRole(String id) async {
    final roles = await listRoles();
    if (roles.length <= 1) throw StateError('至少需要保留一个角色');
    final target = layout.brain(id);
    if (await target.exists()) await target.delete(recursive: true);
  }

  @override
  File? resolveAsset(CompanionRole role, String relativePath) {
    if (relativePath.isEmpty) return null;
    final root = p.normalize(layout.brain(role.id).absolute.path);
    final candidate = p.normalize(p.join(root, relativePath));
    if (!p.isWithin(root, candidate)) return null;
    return File(candidate);
  }

  bool _validId(String value) => RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(value);
}
