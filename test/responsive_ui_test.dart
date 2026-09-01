import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image_codec;

import 'package:rootlink/app/app_state.dart';
import 'package:rootlink/app/theme.dart';
import 'package:rootlink/data/storage_layout.dart';
import 'package:rootlink/domain/models.dart';
import 'package:rootlink/features/roles/role_editor_page.dart';
import 'package:rootlink/main.dart';

import 'test_fixtures.dart';

void main() {
  goldenFileComparator = _TolerantGoldenComparator(Platform.script);

  late Directory root;
  late AppDependencies dependencies;
  late List<CompanionRole> roles;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('rootlink-widget-');
    dependencies = AppDependencies(StorageLayout.forRoot(root));
    roles = <CompanionRole>[fixtureRole()];
    await dependencies.roles.saveRole(roles.first);
  });

  tearDown(() => root.delete(recursive: true));

  Future<void> pumpAt(
    WidgetTester tester,
    Size size, {
    bool dark = false,
    SettingsController? settingsController,
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          dependenciesProvider.overrideWithValue(dependencies),
          settingsProvider.overrideWith(
            (ref) =>
                settingsController ??
                SettingsController(dependencies, UiSettings(isDark: dark)),
          ),
          rolesProvider.overrideWith(
            (ref) => RolesController(dependencies, roles),
          ),
        ],
        child: const RootLinkApp(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  }

  testWidgets('390px uses compact bottom navigation', (tester) async {
    await pumpAt(tester, const Size(390, 844));
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('你的角色'), findsOneWidget);
  });

  testWidgets('home theme button switches between day and night modes', (
    tester,
  ) async {
    final controller = _MemorySettingsController(
      dependencies,
      const UiSettings(),
    );
    await pumpAt(tester, const Size(390, 844), settingsController: controller);

    expect(find.byTooltip('切换到夜晚模式'), findsOneWidget);
    await tester.tap(find.byTooltip('切换到夜晚模式'));
    await tester.pump();

    expect(controller.state.isDark, isTrue);
    expect(find.byTooltip('切换到白天模式'), findsOneWidget);
  });

  testWidgets('840px switches to desktop sidebar', (tester) async {
    await pumpAt(tester, const Size(840, 900));
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.text('设置'), findsOneWidget);
    expect(find.text('露娜'), findsWidgets);
  });

  testWidgets('1200px navigates settings, chat and immersive mode', (
    tester,
  ) async {
    await pumpAt(tester, const Size(1200, 900));
    await tester.tap(find.text('设置').last);
    await tester.pump(const Duration(milliseconds: 250));
    expect(find.text('对话模型'), findsOneWidget);
    expect(find.text('导出当前角色'), findsNothing);

    await tester.tap(find.text('露娜').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    expect(find.byTooltip('沉浸模式'), findsOneWidget);
    await tester.tap(find.byTooltip('沉浸模式'));
    await tester.pump(const Duration(milliseconds: 250));
    expect(find.textContaining('点击继续'), findsOneWidget);
  });

  testWidgets('role editor exposes all five creation steps', (tester) async {
    tester.view.physicalSize = const Size(760, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          dependenciesProvider.overrideWithValue(dependencies),
          rolesProvider.overrideWith(
            (ref) => RolesController(dependencies, roles),
          ),
        ],
        child: const MaterialApp(home: RoleEditorPage()),
      ),
    );
    await tester.enterText(find.byType(TextFormField).at(0), 'new_role');
    await tester.enterText(find.byType(TextFormField).at(1), '新角色');
    for (final title in const <String>['角色立绘', '人格', '角色记忆', '语言风格']) {
      await tester.tap(find.widgetWithText(FilledButton, '下一步'));
      await tester.pump(const Duration(milliseconds: 250));
      expect(find.text(title), findsWidgets);
    }
  });

  testWidgets(
    'memory editor shows editable categories and read-only summaries',
    (tester) async {
      final role = fixtureRole().copyWith(
        memories: <String, dynamic>{
          'episodic_memories': <Object>[
            <String, dynamic>{
              'id': 'e1',
              'content': '第一次一起听雨',
              'memory_type': 'episodic',
              'timestamp': 1,
            },
          ],
          'preference_memories': <Object>[],
          'fact_memories': <Object>[],
          'daily_summary_memories': <Object>[
            <String, dynamic>{'summary_text': '今天聊了音乐'},
          ],
          'monthly_summary_memories': <Object>[
            <String, dynamic>{'content': '本月关系更亲近'},
          ],
        },
      );
      await _pumpEditor(tester, dependencies, roles, role: role);
      for (var index = 0; index < 3; index++) {
        await tester.tap(find.widgetWithText(FilledButton, '下一步'));
        await tester.pump(const Duration(milliseconds: 250));
      }

      expect(find.text('情节记忆'), findsWidgets);
      expect(find.text('偏好记忆'), findsWidgets);
      expect(find.text('事实记忆'), findsWidgets);
      expect(find.text('日度总结'), findsOneWidget);
      expect(find.text('月度总结'), findsOneWidget);
      expect(find.text('第一次一起听雨'), findsOneWidget);
      expect(find.text('今天聊了音乐'), findsOneWidget);
      expect(find.text('本月关系更亲近'), findsOneWidget);
      expect(find.text('只读'), findsNWidgets(2));
      expect(find.text('添加记忆'), findsWidgets);
    },
  );

  testWidgets('editing role saves current draft before explicit export', (
    tester,
  ) async {
    CompanionRole? exported;
    var persistedBeforeExport = false;
    final controller = _RecordingRolesController(dependencies, roles);
    await _pumpEditor(
      tester,
      dependencies,
      roles,
      role: roles.first,
      rolesController: controller,
      onExport: (role) async {
        persistedBeforeExport = controller.savedRole?.name == '露娜（已编辑）';
        exported = role;
      },
    );
    final nameField = find.byType(TextFormField).at(1);
    await tester.enterText(nameField, '露娜（已编辑）');
    await tester.tap(find.byTooltip('保存并导出角色'));
    for (var index = 0; index < 10 && exported == null; index++) {
      await tester.pump();
    }

    expect(exported?.name, '露娜（已编辑）');
    expect(persistedBeforeExport, isTrue);
    expect(find.text('编辑角色'), findsOneWidget);
    expect(controller.savedRole?.name, '露娜（已编辑）');
  });

  testWidgets('light compact home matches visual baseline', (tester) async {
    await pumpAt(tester, const Size(390, 844));
    await expectLater(
      find.byType(RootLinkApp),
      matchesGoldenFile('goldens/home_390_light.png'),
    );
  });

  testWidgets('dark desktop home matches visual baseline', (tester) async {
    await pumpAt(tester, const Size(1200, 900), dark: true);
    await expectLater(
      find.byType(RootLinkApp),
      matchesGoldenFile('goldens/home_1200_dark.png'),
    );
  });

  testWidgets('840px settings matches visual baseline', (tester) async {
    await pumpAt(tester, const Size(840, 900));
    await tester.tap(find.text('设置').last);
    await tester.pump(const Duration(milliseconds: 250));
    await expectLater(
      find.byType(RootLinkApp),
      matchesGoldenFile('goldens/settings_840_light.png'),
    );
  });

  testWidgets('1200px dark chat matches visual baseline', (tester) async {
    await pumpAt(tester, const Size(1200, 900), dark: true);
    await tester.tap(find.text('露娜').first);
    await tester.pump(const Duration(milliseconds: 250));
    await expectLater(
      find.byType(RootLinkApp),
      matchesGoldenFile('goldens/chat_1200_dark.png'),
    );
  });

  testWidgets('840px dark memory editor matches visual baseline', (
    tester,
  ) async {
    await _pumpEditor(
      tester,
      dependencies,
      roles,
      role: roles.first,
      size: const Size(840, 900),
      dark: true,
    );
    for (var index = 0; index < 3; index++) {
      await tester.tap(find.widgetWithText(FilledButton, '下一步'));
      await tester.pump(const Duration(milliseconds: 250));
    }
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/memory_editor_840_dark.png'),
    );
  });
}

Future<void> _pumpEditor(
  WidgetTester tester,
  AppDependencies dependencies,
  List<CompanionRole> roles, {
  CompanionRole? role,
  RoleExportCallback? onExport,
  RolesController? rolesController,
  Size size = const Size(760, 900),
  bool dark = false,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        dependenciesProvider.overrideWithValue(dependencies),
        rolesProvider.overrideWith(
          (ref) => rolesController ?? RolesController(dependencies, roles),
        ),
      ],
      child: MaterialApp(
        theme: buildRootLinkTheme(dark: false),
        darkTheme: buildRootLinkTheme(dark: true),
        themeMode: dark ? ThemeMode.dark : ThemeMode.light,
        home: RoleEditorPage(role: role, onExport: onExport),
      ),
    ),
  );
  await tester.pump();
}

class _RecordingRolesController extends RolesController {
  _RecordingRolesController(super.dependencies, super.initial);

  CompanionRole? savedRole;

  @override
  Future<void> save(CompanionRole role) async {
    savedRole = role;
    state = RolesState(roles: <CompanionRole>[role], selectedId: role.id);
  }
}

class _MemorySettingsController extends SettingsController {
  _MemorySettingsController(super.dependencies, super.state);

  @override
  Future<void> toggleTheme() async {
    state = state.copyWith(isDark: !state.isDark);
  }
}

class _TolerantGoldenComparator extends LocalFileComparator {
  _TolerantGoldenComparator(super.testFile);

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final goldenFile = File.fromUri(getTestUri(golden, null));
    if (!await goldenFile.exists()) return super.compare(imageBytes, golden);
    final actual = image_codec.decodePng(imageBytes);
    final expected = image_codec.decodePng(await goldenFile.readAsBytes());
    if (actual == null ||
        expected == null ||
        actual.width != expected.width ||
        actual.height != expected.height) {
      return false;
    }
    var different = 0;
    final total = actual.width * actual.height;
    for (var y = 0; y < actual.height; y++) {
      for (var x = 0; x < actual.width; x++) {
        final left = actual.getPixel(x, y);
        final right = expected.getPixel(x, y);
        final distance =
            (left.r - right.r).abs() +
            (left.g - right.g).abs() +
            (left.b - right.b).abs() +
            (left.a - right.a).abs();
        if (distance > 18) different++;
      }
    }
    return different / total <= 0.01;
  }
}
