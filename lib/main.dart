import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart' hide XFile;

import 'app/app_state.dart';
import 'app/theme.dart';
import 'data/storage_layout.dart';
import 'domain/models.dart';
import 'features/chat/chat_page.dart';
import 'features/home/home_page.dart';
import 'features/roles/role_editor_page.dart';
import 'features/settings/settings_page.dart';
import 'features/shared/role_avatar.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final layout = await StorageLayout.initialize();
  final dependencies = AppDependencies(layout);
  final settings = await dependencies.settings.load();
  final roles = await dependencies.roles.listRoles();
  runApp(
    ProviderScope(
      overrides: <Override>[
        dependenciesProvider.overrideWithValue(dependencies),
        settingsProvider.overrideWith(
          (ref) => SettingsController(dependencies, settings),
        ),
        rolesProvider.overrideWith(
          (ref) => RolesController(dependencies, roles),
        ),
      ],
      child: const RootLinkApp(),
    ),
  );
}

class RootLinkApp extends ConsumerWidget {
  const RootLinkApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);
    return MaterialApp(
      title: 'RootLink',
      debugShowCheckedModeBanner: false,
      theme: buildRootLinkTheme(dark: false),
      darkTheme: buildRootLinkTheme(dark: true),
      themeMode: settings.isDark ? ThemeMode.dark : ThemeMode.light,
      home: const RootLinkShell(),
    );
  }
}

enum _WorkspacePage { home, chat, settings }

class RootLinkShell extends ConsumerStatefulWidget {
  const RootLinkShell({super.key});

  @override
  ConsumerState<RootLinkShell> createState() => _RootLinkShellState();
}

class _RootLinkShellState extends ConsumerState<RootLinkShell> {
  _WorkspacePage _page = _WorkspacePage.home;
  CompanionRole? _chatRole;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final warning = ref.read(dependenciesProvider).layout.migrationWarning;
      if (warning != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(warning),
            duration: const Duration(seconds: 8),
          ),
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final rolesState = ref.watch(rolesProvider);
    if (_chatRole != null) {
      _chatRole =
          rolesState.roles
              .where((role) => role.id == _chatRole!.id)
              .firstOrNull ??
          _chatRole;
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 840;
        final content = _content();
        if (!wide) {
          return Scaffold(
            body: content,
            bottomNavigationBar: _page == _WorkspacePage.chat
                ? null
                : NavigationBar(
                    selectedIndex: _page == _WorkspacePage.settings ? 1 : 0,
                    onDestinationSelected: (index) => setState(() {
                      _page = index == 0
                          ? _WorkspacePage.home
                          : _WorkspacePage.settings;
                    }),
                    destinations: const <NavigationDestination>[
                      NavigationDestination(
                        icon: Icon(Icons.home_outlined),
                        selectedIcon: Icon(Icons.home_rounded),
                        label: '首页',
                      ),
                      NavigationDestination(
                        icon: Icon(Icons.settings_outlined),
                        selectedIcon: Icon(Icons.settings_rounded),
                        label: '设置',
                      ),
                    ],
                  ),
          );
        }
        return Scaffold(
          body: Row(
            children: <Widget>[
              _DesktopSidebar(
                roles: rolesState.roles,
                selectedPage: _page,
                selectedRole: _chatRole,
                onHome: () => setState(() => _page = _WorkspacePage.home),
                onSettings: () =>
                    setState(() => _page = _WorkspacePage.settings),
                onRole: _openChat,
                onCreate: () => _openEditor(),
              ),
              const VerticalDivider(width: 1),
              Expanded(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1200),
                    child: content,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _content() => switch (_page) {
    _WorkspacePage.home => HomePage(
      onOpenChat: _openChat,
      onCreateRole: () => _openEditor(),
      onEditRole: (role) => _openEditor(role),
      onImport: _importRole,
      isDark: ref.watch(settingsProvider).isDark,
      onToggleTheme: _toggleTheme,
    ),
    _WorkspacePage.chat when _chatRole != null => ChatPage(
      role: _chatRole!,
      onBack: () => setState(() => _page = _WorkspacePage.home),
    ),
    _ => SettingsPage(onImport: _importRole),
  };

  Future<void> _toggleTheme() async {
    try {
      await ref.read(settingsProvider.notifier).toggleTheme();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('主题切换失败：$error')));
      }
    }
  }

  void _openChat(CompanionRole role) {
    ref.read(rolesProvider.notifier).select(role.id);
    setState(() {
      _chatRole = role;
      _page = _WorkspacePage.chat;
    });
  }

  Future<void> _openEditor([CompanionRole? role]) async {
    await Navigator.of(context).push<CompanionRole>(
      MaterialPageRoute(
        builder: (_) => RoleEditorPage(role: role, onExport: _exportRole),
      ),
    );
  }

  Future<void> _importRole() async {
    const type = XTypeGroup(
      label: 'RootLink 角色包',
      extensions: <String>['amadues'],
    );
    final source = await openFile(acceptedTypeGroups: const <XTypeGroup>[type]);
    if (source == null) return;
    try {
      final id = await ref
          .read(dependenciesProvider)
          .packages
          .importRole(source.path, overwrite: true);
      await ref.read(rolesProvider.notifier).refresh(selectId: id);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('角色 $id 已导入')));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('导入失败：$error')));
      }
    }
  }

  Future<void> _exportRole(CompanionRole role) async {
    try {
      if (Platform.isWindows) {
        const type = XTypeGroup(
          label: 'RootLink 角色包',
          extensions: <String>['amadues'],
        );
        final location = await getSaveLocation(
          acceptedTypeGroups: const <XTypeGroup>[type],
          suggestedName: '${role.id}.amadues',
        );
        if (location == null) return;
        final path = await ref
            .read(dependenciesProvider)
            .packages
            .exportRole(role.id, location.path);
        if (mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text('已导出到 $path')));
        }
      } else {
        final temp = await getTemporaryDirectory();
        final path = await ref
            .read(dependenciesProvider)
            .packages
            .exportRole(role.id, p.join(temp.path, '${role.id}.amadues'));
        await SharePlus.instance.share(
          ShareParams(
            files: <XFile>[XFile(path)],
            title: '分享 ${role.name} 的角色包',
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('导出失败：$error')));
      }
    }
  }
}

class _DesktopSidebar extends StatelessWidget {
  const _DesktopSidebar({
    required this.roles,
    required this.selectedPage,
    required this.selectedRole,
    required this.onHome,
    required this.onSettings,
    required this.onRole,
    required this.onCreate,
  });

  final List<CompanionRole> roles;
  final _WorkspacePage selectedPage;
  final CompanionRole? selectedRole;
  final VoidCallback onHome;
  final VoidCallback onSettings;
  final ValueChanged<CompanionRole> onRole;
  final VoidCallback onCreate;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 268,
    child: SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 8, 16),
              child: Row(
                children: <Widget>[
                  DecoratedBox(
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.primary,
                      borderRadius: const BorderRadius.all(Radius.circular(12)),
                    ),
                    child: const Padding(
                      padding: EdgeInsets.all(8),
                      child: Icon(
                        Icons.hub_rounded,
                        color: Colors.white,
                        size: 20,
                      ),
                    ),
                  ),
                  const SizedBox(width: 11),
                  Text(
                    'RootLink',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
            ),
            _SidebarTile(
              icon: Icons.home_rounded,
              label: '首页',
              selected: selectedPage == _WorkspacePage.home,
              onTap: onHome,
            ),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Row(
                children: <Widget>[
                  Text('角色', style: Theme.of(context).textTheme.labelLarge),
                  const Spacer(),
                  IconButton(
                    onPressed: onCreate,
                    tooltip: '创建角色',
                    icon: const Icon(Icons.add_rounded, size: 20),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                itemCount: roles.length,
                itemBuilder: (context, index) {
                  final role = roles[index];
                  return _SidebarTile(
                    avatar: RoleAvatar(role: role, radius: 17),
                    label: role.name,
                    selected:
                        selectedPage == _WorkspacePage.chat &&
                        selectedRole?.id == role.id,
                    onTap: () => onRole(role),
                  );
                },
              ),
            ),
            const Divider(),
            _SidebarTile(
              icon: Icons.settings_rounded,
              label: '设置',
              selected: selectedPage == _WorkspacePage.settings,
              onTap: onSettings,
            ),
          ],
        ),
      ),
    ),
  );
}

class _SidebarTile extends StatelessWidget {
  const _SidebarTile({
    this.icon,
    this.avatar,
    required this.label,
    required this.selected,
    required this.onTap,
  });
  final IconData? icon;
  final Widget? avatar;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Material(
      color: selected
          ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.12)
          : Colors.transparent,
      borderRadius: BorderRadius.circular(15),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(15),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
          child: Row(
            children: <Widget>[
              avatar ??
                  Icon(
                    icon,
                    color: selected
                        ? Theme.of(context).colorScheme.primary
                        : null,
                  ),
              const SizedBox(width: 11),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                    color: selected
                        ? Theme.of(context).colorScheme.primary
                        : null,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
