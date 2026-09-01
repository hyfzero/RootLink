import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import '../domain/repositories.dart';
import 'storage_layout.dart';

class CharacterPackageException implements Exception {
  const CharacterPackageException(this.message);
  final String message;
  @override
  String toString() => message;
}

class ZipCharacterPackageService implements CharacterPackageService {
  ZipCharacterPackageService(this.layout);

  final StorageLayout layout;
  static const _format = 'amadues.character-package';
  static const _version = 1;
  static const _root = 'brain';
  static const _maxPackageBytes = 512 * 1024 * 1024;
  static const _maxFileBytes = 128 * 1024 * 1024;
  static const _maxExpandedBytes = 512 * 1024 * 1024;
  static const _maxEntries = 10000;

  @override
  Future<String> exportRole(String roleId, String outputPath) async {
    _validateId(roleId);
    final role = layout.brain(roleId);
    if (!await role.exists()) throw const CharacterPackageException('角色不存在');
    final archive = Archive();
    final fileEntries = <Map<String, dynamic>>[];
    final directories = <String>{};
    await for (final entity in role.list(recursive: true, followLinks: false)) {
      final relative = p.posix.joinAll(
        p.split(p.relative(entity.path, from: role.path)),
      );
      if (_excluded(relative)) continue;
      if (entity is Directory) {
        directories.add(relative);
        continue;
      }
      if (entity is! File) continue;
      final bytes = await entity.readAsBytes();
      fileEntries.add(<String, dynamic>{
        'path': relative,
        'sha256': sha256.convert(bytes).toString(),
        'size': bytes.length,
      });
      for (
        var parent = p.posix.dirname(relative);
        parent != '.';
        parent = p.posix.dirname(parent)
      ) {
        directories.add(parent);
      }
      archive.addFile(ArchiveFile.bytes('$_root/$relative', bytes));
    }
    fileEntries.sort((a, b) => '${a['path']}'.compareTo('${b['path']}'));
    final sortedDirectories = directories.toList()..sort();
    for (final directory in sortedDirectories) {
      archive.addFile(ArchiveFile.directory('$_root/$directory/'));
    }
    final manifest = <String, dynamic>{
      'format': _format,
      'version': _version,
      'exported_at': DateTime.now().toUtc().toIso8601String(),
      'brain_id': roleId,
      'root': _root,
      'directories': sortedDirectories,
      'files': fileEntries,
    };
    archive.addFile(
      ArchiveFile.string(
        'manifest.json',
        const JsonEncoder.withIndent('  ').convert(manifest),
      ),
    );
    final target = outputPath.endsWith('.amadues')
        ? outputPath
        : '$outputPath.amadues';
    final file = File(target);
    await file.parent.create(recursive: true);
    final encoded = await Isolate.run(() => ZipEncoder().encodeBytes(archive));
    await file.writeAsBytes(encoded, flush: true);
    return file.path;
  }

  @override
  Future<String> importRole(String packagePath, {bool overwrite = true}) async {
    final source = File(packagePath);
    if (!await source.exists()) throw const CharacterPackageException('角色包不存在');
    if (await source.length() > _maxPackageBytes) {
      throw const CharacterPackageException('角色包超过 512 MB 限制');
    }
    late final Archive archive;
    try {
      final bytes = await source.readAsBytes();
      archive = await Isolate.run(
        () => ZipDecoder().decodeBytes(bytes, verify: true),
      );
    } catch (_) {
      throw const CharacterPackageException('角色包不是有效的 ZIP 文件');
    }
    final entries = <String, ArchiveFile>{};
    var expandedBytes = 0;
    for (final file in archive) {
      if (entries.length >= _maxEntries) {
        throw const CharacterPackageException('角色包文件数量过多');
      }
      if (file.isFile) {
        if (file.size > _maxFileBytes) {
          throw CharacterPackageException('角色包单个文件过大：${file.name}');
        }
        expandedBytes += file.size;
        if (expandedBytes > _maxExpandedBytes) {
          throw const CharacterPackageException('角色包解压后超过 512 MB 限制');
        }
      }
      if (!_safe(file.name) || entries.containsKey(file.name)) {
        throw CharacterPackageException('角色包包含不安全或重复路径：${file.name}');
      }
      if (file.name != 'manifest.json' && !file.name.startsWith('$_root/')) {
        throw CharacterPackageException('角色包包含未知路径：${file.name}');
      }
      entries[file.name] = file;
    }
    final manifestFile = entries['manifest.json'];
    if (manifestFile == null || !manifestFile.isFile) {
      throw const CharacterPackageException('角色包缺少 manifest.json');
    }
    final manifest = _manifest(manifestFile.content);
    final roleId = (manifest['brain_id'] ?? '').toString();
    _validateId(roleId);
    final listedDirectories = <String>{};
    for (final raw in manifest['directories'] as List? ?? const <Object>[]) {
      final path = raw.toString();
      if (!_safe(path) || path.endsWith('/') || !listedDirectories.add(path)) {
        throw const CharacterPackageException('manifest 目录条目无效');
      }
    }
    final listed = <String, String>{};
    for (final raw in manifest['files'] as List? ?? const <Object>[]) {
      final item = raw is Map
          ? raw.cast<String, dynamic>()
          : <String, dynamic>{};
      final path = (item['path'] ?? '').toString();
      final digest = (item['sha256'] ?? '').toString().toLowerCase();
      if (!_safe(path) ||
          path.endsWith('/') ||
          !RegExp(r'^[0-9a-f]{64}$').hasMatch(digest) ||
          listed.containsKey(path)) {
        throw const CharacterPackageException('manifest 文件条目无效');
      }
      listed[path] = digest;
    }
    final actual = entries.values
        .where((entry) => entry.isFile && entry.name.startsWith('$_root/'))
        .map((entry) => entry.name.substring('$_root/'.length))
        .toSet();
    if (actual.length != listed.length || !actual.containsAll(listed.keys)) {
      throw const CharacterPackageException('manifest 与角色包内容不一致');
    }
    final uuid = const Uuid().v4();
    final stagingRoot = Directory(
      p.join(layout.data.path, '.importing-$roleId-$uuid'),
    );
    final staging = Directory(p.join(stagingRoot.path, roleId));
    final target = layout.brain(roleId);
    final backup = Directory(
      p.join(layout.data.path, '.import-backup-$roleId-$uuid'),
    );
    var movedExisting = false;
    try {
      await staging.create(recursive: true);
      for (final directory in listedDirectories) {
        await Directory(
          p.join(staging.path, p.joinAll(p.posix.split(directory))),
        ).create(recursive: true);
      }
      for (final entry in listed.entries) {
        final archiveFile = entries['$_root/${entry.key}']!;
        final bytes = archiveFile.content;
        if (sha256.convert(bytes).toString() != entry.value) {
          throw CharacterPackageException('角色包校验失败：${entry.key}');
        }
        final destination = File(
          p.join(staging.path, p.joinAll(p.posix.split(entry.key))),
        );
        await destination.parent.create(recursive: true);
        await destination.writeAsBytes(bytes, flush: true);
      }
      if (await target.exists()) {
        if (!overwrite) throw const CharacterPackageException('同 ID 角色已经存在');
        await target.rename(backup.path);
        movedExisting = true;
      }
      await staging.rename(target.path);
      if (await stagingRoot.exists()) await stagingRoot.delete(recursive: true);
      if (await backup.exists()) await backup.delete(recursive: true);
      return roleId;
    } catch (_) {
      if (movedExisting && await target.exists()) {
        await target.delete(recursive: true);
      }
      if (movedExisting && await backup.exists()) {
        await backup.rename(target.path);
      }
      if (await stagingRoot.exists()) await stagingRoot.delete(recursive: true);
      rethrow;
    }
  }

  Map<String, dynamic> _manifest(List<int> bytes) {
    try {
      final value = jsonDecode(utf8.decode(bytes));
      if (value is! Map ||
          value['format'] != _format ||
          value['version'] != _version ||
          value['root'] != _root) {
        throw const FormatException();
      }
      return value.cast<String, dynamic>();
    } catch (_) {
      throw const CharacterPackageException('角色包 manifest 版本不受支持');
    }
  }

  void _validateId(String value) {
    if (!RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(value)) {
      throw const CharacterPackageException('角色 ID 无效');
    }
  }

  bool _safe(String value) {
    if (value.isEmpty ||
        value.contains('\\') ||
        value.contains(':') ||
        value.startsWith('/')) {
      return false;
    }
    return !p.posix.split(value).contains('..');
  }

  bool _excluded(String value) =>
      value.split('/').contains('__pycache__') ||
      value.endsWith('.pyc') ||
      value.endsWith('.pyo') ||
      value.contains('.tmp.');
}
