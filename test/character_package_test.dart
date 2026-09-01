import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

import 'package:rootlink/data/file_role_repository.dart';
import 'package:rootlink/data/storage_layout.dart';
import 'package:rootlink/data/zip_character_package_service.dart';

import 'test_fixtures.dart';

void main() {
  test('v1 character package exports and imports without data loss', () async {
    final sourceRoot = await Directory.systemTemp.createTemp(
      'rootlink-package-src-',
    );
    final targetRoot = await Directory.systemTemp.createTemp(
      'rootlink-package-dst-',
    );
    addTearDown(() async {
      await sourceRoot.delete(recursive: true);
      await targetRoot.delete(recursive: true);
    });
    final sourceLayout = StorageLayout.forRoot(sourceRoot);
    final targetLayout = StorageLayout.forRoot(targetRoot);
    final role = fixtureRole();
    await FileRoleRepository(sourceLayout).saveRole(role);
    await Directory(
      p.join(sourceLayout.brain(role.id).path, 'empty', 'nested'),
    ).create(recursive: true);
    final packagePath = p.join(sourceRoot.path, 'luna.amadues');
    await ZipCharacterPackageService(
      sourceLayout,
    ).exportRole(role.id, packagePath);
    final importedId = await ZipCharacterPackageService(
      targetLayout,
    ).importRole(packagePath);
    final imported = await FileRoleRepository(targetLayout).getRole(importedId);
    expect(imported?.name, role.name);
    expect(imported?.profile['future_profile_field'], <String, dynamic>{
      'kept': true,
    });
    expect(
      await Directory(
        p.join(targetLayout.brain(role.id).path, 'empty', 'nested'),
      ).exists(),
      isTrue,
    );
  });

  test('character package rejects path traversal', () async {
    final root = await Directory.systemTemp.createTemp(
      'rootlink-package-attack-',
    );
    addTearDown(() => root.delete(recursive: true));
    final archive = Archive()
      ..addFile(ArchiveFile.string('../escape.json', '{}'))
      ..addFile(ArchiveFile.string('manifest.json', '{}'));
    final file = File(p.join(root.path, 'attack.amadues'))
      ..writeAsBytesSync(ZipEncoder().encodeBytes(archive));
    expect(
      () => ZipCharacterPackageService(
        StorageLayout.forRoot(root),
      ).importRole(file.path),
      throwsA(isA<CharacterPackageException>()),
    );
  });

  test('invalid overwrite keeps the existing role intact', () async {
    final root = await Directory.systemTemp.createTemp(
      'rootlink-package-rollback-',
    );
    addTearDown(() => root.delete(recursive: true));
    final layout = StorageLayout.forRoot(root);
    await FileRoleRepository(
      layout,
    ).saveRole(fixtureRole(id: 'same_id', name: '保留角色'));
    final profileBytes = utf8.encode('{"name":"损坏角色"}');
    final manifest = <String, dynamic>{
      'format': 'amadues.character-package',
      'version': 1,
      'brain_id': 'same_id',
      'root': 'brain',
      'directories': <String>['persona'],
      'files': <Object>[
        <String, dynamic>{
          'path': 'persona/profile.json',
          'sha256': sha256.convert(utf8.encode('different')).toString(),
          'size': profileBytes.length,
        },
      ],
    };
    final archive = Archive()
      ..addFile(ArchiveFile.string('manifest.json', jsonEncode(manifest)))
      ..addFile(ArchiveFile.bytes('brain/persona/profile.json', profileBytes));
    final package = File(p.join(root.path, 'invalid-overwrite.amadues'));
    await package.writeAsBytes(ZipEncoder().encodeBytes(archive));

    await expectLater(
      ZipCharacterPackageService(layout).importRole(package.path),
      throwsA(isA<CharacterPackageException>()),
    );
    final preserved = await FileRoleRepository(layout).getRole('same_id');
    expect(preserved?.name, '保留角色');
  });
}
