import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;

class AtomicJsonStore {
  const AtomicJsonStore();

  Future<Map<String, dynamic>> readMap(
    File file, {
    Map<String, dynamic> fallback = const <String, dynamic>{},
  }) async {
    if (!await file.exists()) {
      return Map<String, dynamic>.from(fallback);
    }
    final value = jsonDecode(await file.readAsString());
    if (value is! Map) {
      throw const FormatException('JSON root must be an object');
    }
    return value.map((key, item) => MapEntry(key.toString(), item));
  }

  Future<void> writeMap(File target, Map<String, dynamic> value) async {
    await target.parent.create(recursive: true);
    final suffix = '${pid}_${DateTime.now().microsecondsSinceEpoch}';
    final temporary = File('${target.path}.tmp.$suffix');
    final backup = File('${target.path}.bak');
    await temporary.writeAsString(
      const JsonEncoder.withIndent('  ').convert(value),
      flush: true,
    );
    // Read the temporary file back before replacing a known-good document.
    final checked = jsonDecode(await temporary.readAsString());
    if (checked is! Map) {
      await temporary.delete();
      throw const FormatException('Refusing to persist invalid JSON');
    }
    var movedOriginal = false;
    try {
      if (await target.exists()) {
        if (await backup.exists()) {
          await backup.delete();
        }
        await target.rename(backup.path);
        movedOriginal = true;
      }
      await temporary.rename(target.path);
    } catch (_) {
      if (await target.exists()) {
        await target.delete();
      }
      if (movedOriginal && await backup.exists()) {
        await backup.rename(target.path);
      }
      if (await temporary.exists()) {
        await temporary.delete();
      }
      rethrow;
    }
  }

  Future<void> copyMissingTree(Directory source, Directory target) async {
    if (!await source.exists()) {
      return;
    }
    await target.create(recursive: true);
    await for (final entity in source.list(
      recursive: true,
      followLinks: false,
    )) {
      final relative = p.relative(entity.path, from: source.path);
      final destination = p.join(target.path, relative);
      if (entity is Directory) {
        await Directory(destination).create(recursive: true);
      } else if (entity is File && !await File(destination).exists()) {
        await File(destination).parent.create(recursive: true);
        await entity.copy(destination);
      }
    }
  }
}
