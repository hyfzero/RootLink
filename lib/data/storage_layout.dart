import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'atomic_json.dart';

class StorageLayout {
  StorageLayout._({required this.root});

  factory StorageLayout.forRoot(Directory root) => StorageLayout._(root: root);

  final Directory root;
  final AtomicJsonStore json = const AtomicJsonStore();
  String? migrationWarning;

  Directory get data => Directory(p.join(root.path, 'data'));
  Directory get config => Directory(p.join(root.path, 'config'));
  File get migrationMarker =>
      File(p.join(root.path, '.amadues_storage_migration_v1'));
  Directory brain(String id) => Directory(p.join(data.path, id));

  static Future<StorageLayout> initialize() async {
    final rootOverride = Platform.environment['ROOTLINK_STORAGE_ROOT'];
    final dataOverride = Platform.environment['AGENT_DATA_DIR'];
    final configOverride = Platform.environment['AGENT_CONFIG_DIR'];
    final fletOverride = Platform.environment['FLET_APP_STORAGE_DATA'];
    final configuredRoot = rootOverride ?? fletOverride;
    final root = configuredRoot == null || configuredRoot.isEmpty
        ? await getApplicationSupportDirectory()
        : Directory(configuredRoot);
    final layout = StorageLayout._(root: root);
    await root.create(recursive: true);
    try {
      if (dataOverride?.isNotEmpty == true) {
        await layout._copyValidated(
          sourceData: Directory(dataOverride!),
          sourceConfig: null,
        );
      }
      if (configOverride?.isNotEmpty == true) {
        await layout._copyValidated(
          sourceData: null,
          sourceConfig: Directory(configOverride!),
        );
      }
    } catch (error) {
      layout.migrationWarning = '指定的旧数据目录未能迁移，原数据已保留：$error';
    }
    await layout._migrateLegacy();
    await layout.data.create(recursive: true);
    await layout.config.create(recursive: true);
    return layout;
  }

  Future<void> _migrateLegacy() async {
    if (await migrationMarker.exists()) return;
    final candidates = <Directory>[];
    candidates.add(root);
    candidates.add(Directory(p.join(root.path, 'app_storage')));
    candidates.add(Directory(p.join(root.path, 'files')));
    if (Platform.isWindows) {
      final local = Platform.environment['LOCALAPPDATA'];
      final roaming = Platform.environment['APPDATA'];
      final appData = local?.isNotEmpty == true ? local! : roaming;
      if (appData != null && appData.isNotEmpty) {
        candidates.add(Directory(p.join(appData, 'amadues')));
        final packages = Directory(p.join(appData, 'Packages'));
        if (await packages.exists()) {
          await for (final entity in packages.list(followLinks: false)) {
            if (entity is Directory &&
                p
                    .basename(entity.path)
                    .startsWith('PythonSoftwareFoundation.Python.')) {
              candidates.add(
                Directory(
                  p.join(entity.path, 'LocalCache', 'Local', 'amadues'),
                ),
              );
            }
          }
        }
      }
    }
    var migrationSucceeded = true;
    for (final source in candidates) {
      if (p.equals(p.normalize(source.path), p.normalize(root.path))) continue;
      final succeeded = await migrateFromLegacyDirectory(source);
      if (!succeeded) {
        migrationSucceeded = false;
      }
    }
    if (migrationSucceeded) {
      await migrationMarker.writeAsString('ok\n', flush: true);
    }
  }

  Future<bool> migrateFromLegacyDirectory(Directory source) async {
    try {
      await _copyValidated(
        sourceData: Directory(p.join(source.path, 'data')),
        sourceConfig: Directory(p.join(source.path, 'config')),
      );
      return true;
    } catch (error) {
      migrationWarning = '旧数据迁移未完成，原数据已保留：$error';
      return false;
    }
  }

  Future<void> _copyValidated({
    required Directory? sourceData,
    required Directory? sourceConfig,
  }) async {
    if (sourceData == null && sourceConfig == null) return;
    final staging = Directory(
      p.join(
        root.path,
        '.migration-staging-${pid}_${DateTime.now().microsecondsSinceEpoch}',
      ),
    );
    try {
      final stagedData = Directory(p.join(staging.path, 'data'));
      final stagedConfig = Directory(p.join(staging.path, 'config'));
      if (sourceData != null) {
        await json.copyMissingTree(sourceData, stagedData);
      }
      if (sourceConfig != null) {
        await json.copyMissingTree(sourceConfig, stagedConfig);
      }
      await _validateJsonTree(staging);
      await json.copyMissingTree(stagedData, data);
      await json.copyMissingTree(stagedConfig, config);
    } finally {
      if (await staging.exists()) {
        await staging.delete(recursive: true);
      }
    }
  }

  Future<void> _validateJsonTree(Directory directory) async {
    if (!await directory.exists()) return;
    await for (final entity in directory.list(
      recursive: true,
      followLinks: false,
    )) {
      if (entity is File && p.extension(entity.path).toLowerCase() == '.json') {
        jsonDecode(await entity.readAsString());
      }
    }
  }

  Future<void> seedBundledRoleIfEmpty() async {
    final existing = await data
        .list(followLinks: false)
        .where((entity) => entity is Directory)
        .isEmpty;
    if (!existing) return;
    final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
    final assets = manifest.listAssets().where(
      (asset) => asset.startsWith('resource/key/'),
    );
    for (final asset in assets) {
      final relative = asset.substring('resource/key/'.length);
      if (relative.isEmpty) continue;
      final target = File(
        p.join(data.path, 'key', p.joinAll(p.posix.split(relative))),
      );
      await target.parent.create(recursive: true);
      final bytes = await rootBundle.load(asset);
      await target.writeAsBytes(bytes.buffer.asUint8List(), flush: true);
    }
  }
}
